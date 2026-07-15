"""Strict extraction of one ChEMBL functional-activity evidence bundle."""

from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.parse
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


CHEMBL_ACTIVITY_JOB_SCHEMA_VERSION = "adds.chembl-activity-ingestion-job.v1"
CHEMBL_PROVIDER_ID = "chembl"

_RESOURCE_KEYS = (
    "status",
    "activity",
    "assay",
    "document",
    "molecule",
    "target",
)
_JOB_FIELDS = frozenset(
    {
        "schema_version",
        "job_id",
        "source_receipt_ids",
        "release",
        "activity",
        "record",
    }
)
_RELEASE_FIELDS = frozenset({"database_version", "release_date"})
_ACTIVITY_FIELDS = frozenset(
    {
        "activity_id",
        "assay_chembl_id",
        "document_chembl_id",
        "molecule_chembl_id",
        "molecule_name",
        "candidate_aliases",
        "target_chembl_id",
        "target_symbol",
        "target_uniprot_accession",
        "document_pubmed_id",
        "document_doi",
        "source_assay_type",
        "source_assay_type_description",
    }
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
_CONTEXT_FIELDS = frozenset(
    {
        "candidate_id",
        "target_id",
        "target_record_id",
        "disease_id",
        "organism",
        "assay_id",
    }
)
_REVIEWER_METADATA_FIELDS = frozenset(
    {
        "assay_name",
        "assay_type",
        "functional_readout",
        "endpoint",
        "endpoint_relation",
        "endpoint_value",
        "endpoint_unit",
        "effect_direction",
    }
)
_EVIDENCE_FIELDS = frozenset({"assay_description", "functional_readout_anchor"})
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_CHEMBL_ID = re.compile(r"^CHEMBL[1-9][0-9]*$")
_UNIPROT_ACCESSION = re.compile(r"^[A-Z0-9]{6,10}$")
_PMID = re.compile(r"^[1-9][0-9]{0,15}$")
_DOI = re.compile(r"^10\.[0-9]{4,9}/[-._;()/:A-Z0-9]+$", re.IGNORECASE)
_DATABASE_VERSION = re.compile(r"^ChEMBL_([1-9][0-9]*)$")
_RELATION_MAP = {"<": "lt", "<=": "le", "=": "eq", ">=": "ge", ">": "gt"}


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


def _chembl_id(value: Any, field_name: str) -> str:
    text = _text(value, field_name).upper()
    if _CHEMBL_ID.fullmatch(text) is None:
        raise ValueError(f"{field_name} must be a canonical ChEMBL identifier")
    return text


def _positive_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _probability(value: Any, field_name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise ValueError(f"{field_name} must be between zero and one")
    return float(value)


def _decimal(value: Any, field_name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(f"{field_name} must be a finite decimal")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{field_name} must be a finite decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{field_name} must be a finite decimal")
    return result


def _iso_date(value: Any, field_name: str) -> date:
    text = _text(value, field_name)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO 8601 calendar date") from exc


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _canonical_text_list(value: Any, field_name: str) -> list[str]:
    values = [
        _text(item, f"{field_name}[{index}]")
        for index, item in enumerate(_sequence(value, field_name))
    ]
    if not values or len(values) > 32:
        raise ValueError(f"{field_name} must contain 1-32 strings")
    normalized = [_normalized(item) for item in values]
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field_name} must not contain duplicate values")
    return values


def _canonical_doi(value: Any, field_name: str) -> str:
    doi = _text(value, field_name).casefold()
    if _DOI.fullmatch(doi) is None:
        raise ValueError(f"{field_name} must be a DOI")
    return doi


def _lineage_ids(activity: Mapping[str, Any]) -> list[str]:
    return [
        f"chembl-document:{activity['document_chembl_id']}",
        f"pubmed:{activity['document_pubmed_id']}",
        f"doi:{activity['document_doi']}",
    ]


def _normalize_release(value: Any) -> tuple[dict[str, str], int, date]:
    release = _mapping(value, "job.release")
    if set(release) != _RELEASE_FIELDS:
        raise ValueError(f"job.release must contain exactly {sorted(_RELEASE_FIELDS)}")
    version = _text(release["database_version"], "job.release.database_version")
    match = _DATABASE_VERSION.fullmatch(version)
    if match is None:
        raise ValueError("job.release.database_version must use ChEMBL_<number>")
    release_date = _iso_date(release["release_date"], "job.release.release_date")
    return (
        {
            "database_version": version,
            "release_date": release_date.isoformat(),
        },
        int(match.group(1)),
        release_date,
    )


def _normalize_activity(value: Any) -> dict[str, Any]:
    activity = _mapping(value, "job.activity")
    if set(activity) != _ACTIVITY_FIELDS:
        raise ValueError(
            f"job.activity must contain exactly {sorted(_ACTIVITY_FIELDS)}"
        )
    aliases = _canonical_text_list(
        activity["candidate_aliases"], "job.activity.candidate_aliases"
    )
    pmid = _text(activity["document_pubmed_id"], "job.activity.document_pubmed_id")
    if _PMID.fullmatch(pmid) is None:
        raise ValueError("job.activity.document_pubmed_id must be a positive PMID")
    accession = _text(
        activity["target_uniprot_accession"],
        "job.activity.target_uniprot_accession",
    ).upper()
    if _UNIPROT_ACCESSION.fullmatch(accession) is None:
        raise ValueError("job.activity.target_uniprot_accession is not canonical")
    normalized = {
        "activity_id": _positive_int(
            activity["activity_id"], "job.activity.activity_id"
        ),
        "assay_chembl_id": _chembl_id(
            activity["assay_chembl_id"], "job.activity.assay_chembl_id"
        ),
        "document_chembl_id": _chembl_id(
            activity["document_chembl_id"], "job.activity.document_chembl_id"
        ),
        "molecule_chembl_id": _chembl_id(
            activity["molecule_chembl_id"], "job.activity.molecule_chembl_id"
        ),
        "molecule_name": _text(activity["molecule_name"], "job.activity.molecule_name"),
        "candidate_aliases": aliases,
        "target_chembl_id": _chembl_id(
            activity["target_chembl_id"], "job.activity.target_chembl_id"
        ),
        "target_symbol": _text(activity["target_symbol"], "job.activity.target_symbol"),
        "target_uniprot_accession": accession,
        "document_pubmed_id": pmid,
        "document_doi": _canonical_doi(
            activity["document_doi"], "job.activity.document_doi"
        ),
        "source_assay_type": _text(
            activity["source_assay_type"], "job.activity.source_assay_type"
        ),
        "source_assay_type_description": _text(
            activity["source_assay_type_description"],
            "job.activity.source_assay_type_description",
        ),
    }
    alias_keys = {_normalized(item) for item in aliases}
    if _normalized(normalized["molecule_name"]) not in alias_keys:
        raise ValueError("job.activity.candidate_aliases must include molecule_name")
    return normalized


def _normalize_record(
    value: Any,
    *,
    source_receipt_id: str,
    release: Mapping[str, str],
    activity: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    record = _mapping(value, "job.record")
    if set(record) != _RECORD_FIELDS:
        raise ValueError(f"job.record must contain exactly {sorted(_RECORD_FIELDS)}")
    if record["predicate"] != "candidate_target_functional_activity_supported":
        raise ValueError(
            "job.record.predicate must be candidate_target_functional_activity_supported"
        )
    observed_at = _iso_date(record["observed_at"], "job.record.observed_at")
    available_at = _iso_date(record["available_at"], "job.record.available_at")
    if observed_at > available_at:
        raise ValueError("job.record.observed_at cannot follow available_at")
    if available_at.isoformat() != release["release_date"]:
        raise ValueError("job.record.available_at must equal the ChEMBL release date")

    context = _mapping(record["biological_context"], "job.record.biological_context")
    if set(context) != _CONTEXT_FIELDS:
        raise ValueError(
            "job.record.biological_context must contain exactly "
            f"{sorted(_CONTEXT_FIELDS)}"
        )
    context = {
        key: _text(value, f"job.record.biological_context.{key}")
        for key, value in context.items()
    }
    if (
        context["candidate_id"] != activity["molecule_chembl_id"]
        or context["target_id"] != activity["target_chembl_id"]
        or context["assay_id"] != activity["assay_chembl_id"]
    ):
        raise ValueError("job.record biological identity does not match job.activity")

    metadata = _mapping(record["metadata"], "job.record.metadata")
    if set(metadata) != _REVIEWER_METADATA_FIELDS:
        raise ValueError(
            "job.record.metadata must contain exactly "
            f"{sorted(_REVIEWER_METADATA_FIELDS)}"
        )
    normalized_metadata = {
        "assay_name": _text(metadata["assay_name"], "job.record.metadata.assay_name"),
        "assay_type": _text(
            metadata["assay_type"], "job.record.metadata.assay_type"
        ).casefold(),
        "functional_readout": metadata["functional_readout"],
        "endpoint": _text(metadata["endpoint"], "job.record.metadata.endpoint"),
        "endpoint_relation": _text(
            metadata["endpoint_relation"], "job.record.metadata.endpoint_relation"
        ).casefold(),
        "endpoint_value": float(
            _decimal(metadata["endpoint_value"], "job.record.metadata.endpoint_value")
        ),
        "endpoint_unit": _text(
            metadata["endpoint_unit"], "job.record.metadata.endpoint_unit"
        ),
        "effect_direction": _text(
            metadata["effect_direction"], "job.record.metadata.effect_direction"
        ),
    }
    if normalized_metadata["assay_type"] != "functional":
        raise ValueError("job.record.metadata.assay_type must be functional")
    if normalized_metadata["functional_readout"] is not True:
        raise ValueError("job.record.metadata.functional_readout must be true")
    if normalized_metadata["endpoint_relation"] not in _RELATION_MAP.values():
        raise ValueError("job.record.metadata.endpoint_relation is unsupported")

    evidence = _mapping(record["evidence"], "job.record.evidence")
    if set(evidence) != _EVIDENCE_FIELDS:
        raise ValueError(
            f"job.record.evidence must contain exactly {sorted(_EVIDENCE_FIELDS)}"
        )
    normalized_evidence = {
        key: _text(item, f"job.record.evidence.{key}") for key, item in evidence.items()
    }
    if len(normalized_evidence["assay_description"]) > 4096:
        raise ValueError("job.record.evidence.assay_description is too long")
    if (
        normalized_evidence["assay_description"].count(
            normalized_evidence["functional_readout_anchor"]
        )
        != 1
    ):
        raise ValueError(
            "job.record.evidence.functional_readout_anchor must occur exactly once"
        )

    alias_keys = {_normalized(item) for item in activity["candidate_aliases"]}
    if _normalized(_text(record["subject"], "job.record.subject")) not in alias_keys:
        raise ValueError(
            "job.record.subject must resolve to a declared candidate alias"
        )
    generic = {
        "source_receipt_id": source_receipt_id,
        "record_id": _safe_id(record["record_id"], "job.record.record_id"),
        "predicate": "candidate_target_functional_activity_supported",
        "subject": _text(record["subject"], "job.record.subject"),
        "object_value": _text(record["object_value"], "job.record.object_value"),
        "observed_at": observed_at.isoformat(),
        "available_at": available_at.isoformat(),
        "confidence": _probability(record["confidence"], "job.record.confidence"),
        "biological_context": context,
        "metadata": {
            **normalized_metadata,
            "source_assay_type": activity["source_assay_type"],
            "source_assay_type_description": activity["source_assay_type_description"],
            "candidate_aliases": activity["candidate_aliases"],
            "source_lineage_ids": _lineage_ids(activity),
        },
    }
    normalize_pinned_ingestion_job(
        {
            "schema_version": INGESTION_JOB_SCHEMA_VERSION,
            "job_id": "chembl-normalization-preview",
            "records": [generic],
        }
    )
    return generic, normalized_evidence


def normalize_chembl_activity_ingestion_job(value: Any) -> dict[str, Any]:
    """Validate a reviewer-authored ChEMBL activity job without source bytes."""

    job = _mapping(value, "job")
    if set(job) != _JOB_FIELDS:
        raise ValueError(f"job must contain exactly {sorted(_JOB_FIELDS)}")
    if job["schema_version"] != CHEMBL_ACTIVITY_JOB_SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {CHEMBL_ACTIVITY_JOB_SCHEMA_VERSION}")
    job_id = _safe_id(job["job_id"], "job.job_id")
    receipts = _mapping(job["source_receipt_ids"], "job.source_receipt_ids")
    if set(receipts) != set(_RESOURCE_KEYS):
        raise ValueError(
            f"job.source_receipt_ids must contain exactly {sorted(_RESOURCE_KEYS)}"
        )
    receipts = {
        key: _safe_id(receipts[key], f"job.source_receipt_ids.{key}")
        for key in _RESOURCE_KEYS
    }
    if len(set(receipts.values())) != len(receipts):
        raise ValueError("job.source_receipt_ids values must be unique")
    release, _, _ = _normalize_release(job["release"])
    activity = _normalize_activity(job["activity"])
    generic, evidence = _normalize_record(
        job["record"],
        source_receipt_id=receipts["activity"],
        release=release,
        activity=activity,
    )
    return {
        "schema_version": CHEMBL_ACTIVITY_JOB_SCHEMA_VERSION,
        "job_id": job_id,
        "source_receipt_ids": receipts,
        "release": release,
        "activity": activity,
        "record": {
            **{
                key: item for key, item in generic.items() if key != "source_receipt_id"
            },
            "metadata": {
                key: generic["metadata"][key] for key in _REVIEWER_METADATA_FIELDS
            },
            "evidence": evidence,
        },
    }


def _json_object(payload: bytes, field_name: str) -> dict[str, Any]:
    try:
        source = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{field_name} must be UTF-8 JSON") from exc

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"{field_name} contains a duplicate JSON key: {key}")
            result[key] = item
        return result

    try:
        value = json.loads(
            source,
            object_pairs_hook=unique_object,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"{field_name} contains a non-finite JSON value: {item}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} could not be parsed as JSON") from exc
    return _mapping(value, field_name)


def _resource_identifier(resource: str, activity: Mapping[str, Any]) -> str | None:
    return {
        "status": None,
        "activity": str(activity["activity_id"]),
        "assay": activity["assay_chembl_id"],
        "document": activity["document_chembl_id"],
        "molecule": activity["molecule_chembl_id"],
        "target": activity["target_chembl_id"],
    }[resource]


def _validate_resource_receipt(
    resource: str,
    bundle: SourceBundle,
    *,
    receipt_id: str,
    release_number: int,
    release_date: date,
    identifier: str | None,
) -> None:
    verify_source_payload(bundle.receipt, bundle.payload)
    receipt = bundle.receipt
    if receipt.receipt_id != receipt_id:
        raise ValueError(f"ChEMBL {resource} receipt_id does not match the job")
    if receipt.media_type.casefold() != "application/json":
        raise ValueError(f"ChEMBL {resource} source must use application/json")
    parsed = urllib.parse.urlsplit(receipt.locator)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"ChEMBL {resource} locator has an invalid port") from exc
    suffix = "status.json" if resource == "status" else f"{resource}/{identifier}.json"
    expected_path = f"/chembl/api/data/{suffix}"
    if (
        parsed.scheme.casefold() != "https"
        or (parsed.hostname or "").casefold() != "www.ebi.ac.uk"
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != expected_path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"ChEMBL {resource} locator must be the exact public API URL")
    version_identifier = "status" if identifier is None else f"{resource}-{identifier}"
    expected_version = f"chembl-{release_number}-{version_identifier}-release-{release_date.isoformat()}"
    if receipt.source_version.casefold() != expected_version.casefold():
        raise ValueError(f"ChEMBL {resource} source_version does not bind the release")
    expected_source_id = (
        "chembl-status" if identifier is None else f"chembl-{resource}-{identifier}"
    )
    if receipt.source_id.casefold() != expected_source_id.casefold():
        raise ValueError(f"ChEMBL {resource} source_id is not canonical")
    if receipt.retrieved_at.date() < release_date:
        raise ValueError(f"ChEMBL {resource} was retrieved before its declared release")


def _field(value: Mapping[str, Any], key: str, label: str) -> Any:
    if key not in value:
        raise ValueError(f"{label} is missing {key}")
    return value[key]


def _source_text(value: Mapping[str, Any], key: str, label: str) -> str:
    return _text(_field(value, key, label), f"{label}.{key}")


def _source_int(value: Mapping[str, Any], key: str, label: str) -> int:
    item = _field(value, key, label)
    if not isinstance(item, int) or isinstance(item, bool):
        raise ValueError(f"{label}.{key} must be an integer")
    return item


def _validate_status(
    source: Mapping[str, Any],
    release: Mapping[str, str],
) -> None:
    if (
        _source_text(source, "chembl_db_version", "ChEMBL status")
        != release["database_version"]
        or _source_text(source, "chembl_release_date", "ChEMBL status")
        != release["release_date"]
        or _source_text(source, "status", "ChEMBL status").upper() != "UP"
    ):
        raise ValueError("ChEMBL status does not match the declared active release")


def _validate_activity_sources(
    sources: Mapping[str, Mapping[str, Any]],
    job: Mapping[str, Any],
) -> dict[str, Any]:
    declared = job["activity"]
    record = job["record"]
    metadata = record["metadata"]
    evidence = record["evidence"]
    activity = sources["activity"]
    assay = sources["assay"]
    document = sources["document"]
    molecule = sources["molecule"]
    target = sources["target"]

    identity_checks = {
        "activity.activity_id": (
            _source_int(activity, "activity_id", "activity"),
            declared["activity_id"],
        ),
        "activity.assay_chembl_id": (
            _source_text(activity, "assay_chembl_id", "activity"),
            declared["assay_chembl_id"],
        ),
        "activity.document_chembl_id": (
            _source_text(activity, "document_chembl_id", "activity"),
            declared["document_chembl_id"],
        ),
        "activity.molecule_chembl_id": (
            _source_text(activity, "molecule_chembl_id", "activity"),
            declared["molecule_chembl_id"],
        ),
        "activity.target_chembl_id": (
            _source_text(activity, "target_chembl_id", "activity"),
            declared["target_chembl_id"],
        ),
        "assay.assay_chembl_id": (
            _source_text(assay, "assay_chembl_id", "assay"),
            declared["assay_chembl_id"],
        ),
        "assay.document_chembl_id": (
            _source_text(assay, "document_chembl_id", "assay"),
            declared["document_chembl_id"],
        ),
        "assay.target_chembl_id": (
            _source_text(assay, "target_chembl_id", "assay"),
            declared["target_chembl_id"],
        ),
        "document.document_chembl_id": (
            _source_text(document, "document_chembl_id", "document"),
            declared["document_chembl_id"],
        ),
        "molecule.molecule_chembl_id": (
            _source_text(molecule, "molecule_chembl_id", "molecule"),
            declared["molecule_chembl_id"],
        ),
        "target.target_chembl_id": (
            _source_text(target, "target_chembl_id", "target"),
            declared["target_chembl_id"],
        ),
    }
    mismatches = sorted(
        label
        for label, (observed, expected) in identity_checks.items()
        if str(observed) != str(expected)
    )
    if mismatches:
        raise ValueError(f"ChEMBL linked resource identity mismatch: {mismatches}")

    assay_description = _source_text(assay, "description", "assay")
    if (
        _source_text(activity, "assay_description", "activity") != assay_description
        or evidence["assay_description"] != assay_description
        or assay_description.count(evidence["functional_readout_anchor"]) != 1
    ):
        raise ValueError(
            "ChEMBL assay description or functional-readout anchor mismatch"
        )
    source_assay_type = _source_text(assay, "assay_type", "assay")
    source_assay_description = _source_text(assay, "assay_type_description", "assay")
    if (
        _source_text(activity, "assay_type", "activity") != source_assay_type
        or source_assay_type != declared["source_assay_type"]
        or source_assay_description != declared["source_assay_type_description"]
    ):
        raise ValueError("ChEMBL source assay classification mismatch")
    if (
        _source_int(assay, "confidence_score", "assay") != 9
        or _source_text(assay, "confidence_description", "assay")
        != "Direct single protein target assigned"
        or _source_text(assay, "relationship_type", "assay") != "D"
    ):
        raise ValueError("ChEMBL assay is not assigned directly to one protein")

    source_relation = _source_text(activity, "standard_relation", "activity")
    if source_relation not in _RELATION_MAP:
        raise ValueError("ChEMBL activity uses an unsupported standard_relation")
    if (
        _source_int(activity, "standard_flag", "activity") != 1
        or _source_int(activity, "potential_duplicate", "activity") != 0
        or _field(activity, "data_validity_comment", "activity") is not None
        or _field(activity, "standard_upper_value", "activity") is not None
        or _field(activity, "standard_text_value", "activity") is not None
    ):
        raise ValueError("ChEMBL activity is not a clean standardized point estimate")
    endpoint_value = _decimal(
        _field(activity, "standard_value", "activity"), "activity.standard_value"
    )
    if (
        _source_text(activity, "standard_type", "activity") != metadata["endpoint"]
        or _RELATION_MAP[source_relation] != metadata["endpoint_relation"]
        or endpoint_value != Decimal(str(metadata["endpoint_value"]))
        or _source_text(activity, "standard_units", "activity")
        != metadata["endpoint_unit"]
    ):
        raise ValueError("ChEMBL typed endpoint does not match the reviewer record")
    pchembl = _decimal(
        _field(activity, "pchembl_value", "activity"), "activity.pchembl_value"
    )

    molecule_name = _source_text(molecule, "pref_name", "molecule")
    if (
        molecule_name != declared["molecule_name"]
        or _source_text(activity, "molecule_pref_name", "activity") != molecule_name
        or _source_text(activity, "parent_molecule_chembl_id", "activity")
        != declared["molecule_chembl_id"]
    ):
        raise ValueError("ChEMBL molecule identity mismatch")
    synonyms = _sequence(
        _field(molecule, "molecule_synonyms", "molecule"), "molecule.molecule_synonyms"
    )
    source_aliases = {_normalized(molecule_name)}
    for index, item in enumerate(synonyms):
        synonym = _mapping(item, f"molecule.molecule_synonyms[{index}]")
        for key in ("molecule_synonym", "synonyms"):
            value = synonym.get(key)
            if isinstance(value, str) and value.strip():
                source_aliases.add(_normalized(value))
    missing_aliases = sorted(
        alias
        for alias in declared["candidate_aliases"]
        if _normalized(alias) not in source_aliases
    )
    if missing_aliases:
        raise ValueError(
            f"ChEMBL molecule is missing declared aliases: {missing_aliases}"
        )

    if (
        _source_text(document, "doc_type", "document") != "PUBLICATION"
        or str(_source_int(document, "pubmed_id", "document"))
        != declared["document_pubmed_id"]
        or _canonical_doi(_field(document, "doi", "document"), "document.doi")
        != declared["document_doi"]
    ):
        raise ValueError("ChEMBL publication lineage mismatch")
    document_year = _source_int(document, "year", "document")
    if document_year != date.fromisoformat(record["observed_at"]).year:
        raise ValueError("ChEMBL document year does not match record.observed_at")

    if (
        _source_text(target, "target_type", "target") != "SINGLE PROTEIN"
        or _source_text(target, "organism", "target")
        != record["biological_context"]["organism"]
        or _source_int(target, "tax_id", "target") != 9606
        or _source_text(activity, "target_organism", "activity")
        != record["biological_context"]["organism"]
    ):
        raise ValueError("ChEMBL target organism or type mismatch")
    components = _sequence(
        _field(target, "target_components", "target"), "target.target_components"
    )
    if len(components) != 1:
        raise ValueError("ChEMBL target must contain exactly one protein component")
    component = _mapping(components[0], "target.target_components[0]")
    if (
        _source_text(component, "accession", "target component")
        != declared["target_uniprot_accession"]
        or _source_text(component, "component_type", "target component") != "PROTEIN"
    ):
        raise ValueError("ChEMBL target component accession mismatch")
    target_synonyms = _sequence(
        _field(component, "target_component_synonyms", "target component"),
        "target component.target_component_synonyms",
    )
    gene_symbols = {
        _source_text(
            _mapping(item, "target synonym"), "component_synonym", "target synonym"
        )
        for item in target_synonyms
        if isinstance(item, Mapping) and item.get("syn_type") == "GENE_SYMBOL"
    }
    if gene_symbols != {declared["target_symbol"]}:
        raise ValueError("ChEMBL target gene-symbol identity mismatch")
    if _source_text(activity, "bao_format", "activity") != _source_text(
        assay, "bao_format", "assay"
    ):
        raise ValueError("ChEMBL BAO assay format mismatch")

    return {
        "assay_description": assay_description,
        "pchembl_value": float(pchembl),
        "document_title": _source_text(document, "title", "document"),
        "document_year": document_year,
        "target_name": _source_text(target, "pref_name", "target"),
        "bao_endpoint": _source_text(activity, "bao_endpoint", "activity"),
        "bao_format": _source_text(activity, "bao_format", "activity"),
        "assay_confidence_score": 9,
        "activity_record_id": _source_int(activity, "record_id", "activity"),
    }


def extract_chembl_activity_ingestion_job(
    value: Any,
    bundles: Mapping[str, SourceBundle],
) -> dict[str, Any]:
    """Verify six ChEMBL resources and emit one payload-free generic record."""

    job = normalize_chembl_activity_ingestion_job(value)
    if not isinstance(bundles, Mapping) or set(bundles) != set(_RESOURCE_KEYS):
        raise ValueError(f"bundles must contain exactly {sorted(_RESOURCE_KEYS)}")
    release, release_number, release_date = _normalize_release(job["release"])
    parsed_sources: dict[str, dict[str, Any]] = {}
    retrieval_dates: set[date] = set()
    for resource in _RESOURCE_KEYS:
        bundle = bundles[resource]
        if not isinstance(bundle, SourceBundle):
            raise TypeError(f"bundles[{resource}] must be a SourceBundle")
        identifier = _resource_identifier(resource, job["activity"])
        _validate_resource_receipt(
            resource,
            bundle,
            receipt_id=job["source_receipt_ids"][resource],
            release_number=release_number,
            release_date=release_date,
            identifier=identifier,
        )
        retrieval_dates.add(bundle.receipt.retrieved_at.date())
        parsed_sources[resource] = _json_object(
            bundle.payload, f"ChEMBL {resource} payload"
        )
    if len(retrieval_dates) != 1:
        raise ValueError("ChEMBL resource bundle must come from one retrieval date")
    _validate_status(parsed_sources["status"], release)
    verified = _validate_activity_sources(parsed_sources, job)

    record = job["record"]
    activity = job["activity"]
    linked_receipts = {
        resource: {
            "receipt_id": bundles[resource].receipt.receipt_id,
            "source_id": bundles[resource].receipt.source_id,
            "source_version": bundles[resource].receipt.source_version,
            "content_hash": bundles[resource].receipt.content_hash,
        }
        for resource in _RESOURCE_KEYS
    }
    metadata = {
        **record["metadata"],
        "source_assay_type": activity["source_assay_type"],
        "source_assay_type_description": activity["source_assay_type_description"],
        "candidate_aliases": activity["candidate_aliases"],
        "source_lineage_ids": _lineage_ids(activity),
        "provider_id": CHEMBL_PROVIDER_ID,
        "chembl_database_version": release["database_version"],
        "chembl_release_date": release["release_date"],
        "activity_id": activity["activity_id"],
        "activity_record_id": verified["activity_record_id"],
        "assay_chembl_id": activity["assay_chembl_id"],
        "document_chembl_id": activity["document_chembl_id"],
        "molecule_chembl_id": activity["molecule_chembl_id"],
        "molecule_name": activity["molecule_name"],
        "target_chembl_id": activity["target_chembl_id"],
        "target_symbol": activity["target_symbol"],
        "target_uniprot_accession": activity["target_uniprot_accession"],
        "document_pubmed_id": activity["document_pubmed_id"],
        "document_doi": activity["document_doi"],
        "document_title": verified["document_title"],
        "document_year": verified["document_year"],
        "target_name": verified["target_name"],
        "pchembl_value": verified["pchembl_value"],
        "bao_endpoint": verified["bao_endpoint"],
        "bao_format": verified["bao_format"],
        "assay_confidence_score": verified["assay_confidence_score"],
        "assay_description_sha256": hashlib.sha256(
            verified["assay_description"].encode("utf-8")
        ).hexdigest(),
        "functional_readout_anchor_sha256": hashlib.sha256(
            record["evidence"]["functional_readout_anchor"].encode("utf-8")
        ).hexdigest(),
        "linked_source_receipts": linked_receipts,
    }
    return normalize_pinned_ingestion_job(
        {
            "schema_version": INGESTION_JOB_SCHEMA_VERSION,
            "job_id": job["job_id"],
            "records": [
                {
                    "source_receipt_id": job["source_receipt_ids"]["activity"],
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
