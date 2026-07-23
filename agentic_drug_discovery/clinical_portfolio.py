"""Atomic multi-trial ClinicalTrials.gov source-bundle portfolio extraction."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .clinical_endpoint_mapping import (
    ClinicalEndpointMappingSpec,
    clinical_endpoint_mapping_spec_from_dict,
    clinical_endpoint_mapping_spec_to_dict,
)
from .clinicaltrials_gov import (
    extract_clinicaltrials_gov_ingestion_job,
    normalize_clinicaltrials_gov_ingestion_job,
)
from .ingestion import (
    INGESTION_JOB_SCHEMA_VERSION,
    SourceBundle,
    normalize_pinned_ingestion_job,
)


CLINICALTRIALS_GOV_PORTFOLIO_JOB_SCHEMA_VERSION = (
    "adds.clinicaltrials-gov-portfolio-job.v1"
)
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,191}$")
_JOB_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,191}$")
_NCT_ID = re.compile(r"^NCT[0-9]{8}$")
_PORTFOLIO_FIELDS = frozenset(
    {"schema_version", "portfolio_id", "endpoint_mapping", "trials"}
)
_TRIAL_REFERENCE_FIELDS = frozenset(
    {
        "job_id",
        "source_receipt_id",
        "trial_id",
        "design_id",
        "endpoint_id",
        "safety_id",
    }
)


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be an object")
    return dict(value)


def _sequence(value: Any, path: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{path} must be an array")
    return tuple(value)


def _safe_id(value: Any, path: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise ValueError(f"{path} must be a safe identifier")
    return value


def _trial_reference(value: Any, path: str) -> dict[str, str]:
    data = _mapping(value, path)
    if set(data) != _TRIAL_REFERENCE_FIELDS:
        raise ValueError(
            f"{path} must contain exactly {sorted(_TRIAL_REFERENCE_FIELDS)}"
        )
    trial_id = _safe_id(data["trial_id"], f"{path}.trial_id")
    if _NCT_ID.fullmatch(trial_id) is None:
        raise ValueError(f"{path}.trial_id must be an NCT identifier")
    return {
        field: _safe_id(data[field], f"{path}.{field}")
        for field in sorted(_TRIAL_REFERENCE_FIELDS)
    }


def _reference_key(value: Mapping[str, str]) -> tuple[str, str, str, str]:
    return (
        value["trial_id"],
        value["design_id"],
        value["endpoint_id"],
        value["safety_id"],
    )


def _mapping_key(spec: ClinicalEndpointMappingSpec) -> tuple[
    tuple[str, str, str, str], ...
]:
    return tuple(
        (item.trial_id, item.design_id, item.endpoint_id, item.safety_id)
        for item in spec.bindings
    )


def normalize_clinicaltrials_gov_portfolio_job(value: Any) -> dict[str, Any]:
    """Validate a portfolio declaration without reading local jobs or bundles."""

    data = _mapping(value, "portfolio")
    if set(data) != _PORTFOLIO_FIELDS:
        raise ValueError(
            f"portfolio must contain exactly {sorted(_PORTFOLIO_FIELDS)}"
        )
    if data["schema_version"] != CLINICALTRIALS_GOV_PORTFOLIO_JOB_SCHEMA_VERSION:
        raise ValueError(
            "schema_version must be "
            f"{CLINICALTRIALS_GOV_PORTFOLIO_JOB_SCHEMA_VERSION}"
        )
    portfolio_id = _safe_id(data["portfolio_id"], "portfolio.portfolio_id")
    if _JOB_ID.fullmatch(portfolio_id) is None:
        raise ValueError(
            "portfolio.portfolio_id must also be a valid generic ingestion job id"
        )
    mapping = clinical_endpoint_mapping_spec_from_dict(
        data["endpoint_mapping"], "portfolio.endpoint_mapping"
    )
    if mapping.portfolio_id != portfolio_id:
        raise ValueError("endpoint mapping portfolio_id does not match portfolio")
    raw_trials = _sequence(data["trials"], "portfolio.trials")
    if len(raw_trials) < 2 or len(raw_trials) > 64:
        raise ValueError("portfolio.trials must contain between 2 and 64 trials")
    trials = tuple(
        _trial_reference(item, f"portfolio.trials[{index}]")
        for index, item in enumerate(raw_trials)
    )
    for label, values in (
        ("job ids", tuple(item["job_id"] for item in trials)),
        ("receipt ids", tuple(item["source_receipt_id"] for item in trials)),
        ("trial ids", tuple(item["trial_id"] for item in trials)),
        ("design ids", tuple(item["design_id"] for item in trials)),
        ("endpoint ids", tuple(item["endpoint_id"] for item in trials)),
        ("safety ids", tuple(item["safety_id"] for item in trials)),
    ):
        if len(values) != len(set(values)):
            raise ValueError(f"portfolio trials must use unique {label}")
    if tuple(_reference_key(item) for item in trials) != _mapping_key(mapping):
        raise ValueError(
            "portfolio trial references must exactly match endpoint mapping bindings"
        )
    return {
        "schema_version": CLINICALTRIALS_GOV_PORTFOLIO_JOB_SCHEMA_VERSION,
        "portfolio_id": portfolio_id,
        "endpoint_mapping": clinical_endpoint_mapping_spec_to_dict(mapping),
        "trials": [dict(item) for item in trials],
    }


def extract_clinicaltrials_gov_portfolio_job(
    value: Any,
    trial_jobs: Sequence[Any],
    bundles: Mapping[str, SourceBundle],
) -> dict[str, Any]:
    """Verify every declared job/bundle before emitting one payload-free job."""

    portfolio = normalize_clinicaltrials_gov_portfolio_job(value)
    mapping = clinical_endpoint_mapping_spec_from_dict(
        portfolio["endpoint_mapping"], "portfolio.endpoint_mapping"
    )
    raw_jobs = _sequence(trial_jobs, "trial_jobs")
    normalized_jobs: dict[str, dict[str, Any]] = {}
    for index, raw_job in enumerate(raw_jobs):
        job = normalize_clinicaltrials_gov_ingestion_job(raw_job)
        job_id = job["job_id"]
        if job_id in normalized_jobs:
            raise ValueError(f"duplicate ClinicalTrials.gov trial job: {job_id}")
        normalized_jobs[job_id] = job
    expected_job_ids = {item["job_id"] for item in portfolio["trials"]}
    if set(normalized_jobs) != expected_job_ids:
        missing = sorted(expected_job_ids - set(normalized_jobs))
        extra = sorted(set(normalized_jobs) - expected_job_ids)
        raise ValueError(
            f"trial job set mismatch; missing={missing}, unexpected={extra}"
        )
    if not isinstance(bundles, Mapping):
        raise TypeError("bundles must map receipt ids to SourceBundle values")
    normalized_bundles: dict[str, SourceBundle] = {}
    for key, bundle in bundles.items():
        receipt_id = _safe_id(key, "bundles receipt id")
        if not isinstance(bundle, SourceBundle):
            raise TypeError("bundles values must be SourceBundle records")
        if receipt_id != bundle.receipt.receipt_id:
            raise ValueError("bundle key must equal its receipt_id")
        normalized_bundles[receipt_id] = bundle
    expected_receipt_ids = {
        item["source_receipt_id"] for item in portfolio["trials"]
    }
    if set(normalized_bundles) != expected_receipt_ids:
        missing = sorted(expected_receipt_ids - set(normalized_bundles))
        extra = sorted(set(normalized_bundles) - expected_receipt_ids)
        raise ValueError(
            f"source bundle set mismatch; missing={missing}, unexpected={extra}"
        )
    content_hashes = tuple(
        bundle.receipt.content_hash for bundle in normalized_bundles.values()
    )
    if len(content_hashes) != len(set(content_hashes)):
        raise ValueError("portfolio source bundles must be content-hash disjoint")
    if any(
        mapping.review.reviewed_at < bundle.receipt.retrieved_at
        for bundle in normalized_bundles.values()
    ):
        raise ValueError("endpoint mapping review predates source bundle retrieval")

    extracted_records: list[dict[str, Any]] = []
    trial_count = len(portfolio["trials"])
    for index, reference in enumerate(portfolio["trials"]):
        job = normalized_jobs[reference["job_id"]]
        trial = job["trial"]
        expected = {
            "source_receipt_id": job["source_receipt_id"],
            "trial_id": trial["nct_id"],
            "design_id": f"{trial['nct_id']}:design",
            "endpoint_id": trial["endpoint"]["endpoint_id"],
            "safety_id": trial["safety"]["safety_id"],
        }
        for field_name, expected_value in expected.items():
            if reference[field_name] != expected_value:
                raise ValueError(
                    f"portfolio reference {field_name} does not match trial job "
                    f"{reference['job_id']}"
                )
        if (
            trial["candidate_id"] != mapping.candidate_id
            or trial["intervention_id"] != mapping.intervention_id
            or trial["disease_id"] != mapping.disease_id
        ):
            raise ValueError(
                f"trial job identity does not match endpoint mapping: {job['job_id']}"
            )
        bundle = normalized_bundles[reference["source_receipt_id"]]
        extracted = extract_clinicaltrials_gov_ingestion_job(job, bundle)
        if len(extracted["records"]) != 1:
            raise ValueError("ClinicalTrials.gov trial extraction must emit one record")
        record = dict(extracted["records"][0])
        metadata = dict(record["metadata"])
        metadata["clinical_portfolio"] = {
            "portfolio_id": portfolio["portfolio_id"],
            "endpoint_mapping_id": mapping.mapping_id,
            "endpoint_family_id": mapping.endpoint_family_id,
            "trial_index": index,
            "trial_count": trial_count,
            "source_disjoint_by_content_hash": True,
            "automatic_endpoint_mapping_performed": False,
        }
        record["metadata"] = metadata
        extracted_records.append(record)

    return normalize_pinned_ingestion_job(
        {
            "schema_version": INGESTION_JOB_SCHEMA_VERSION,
            "job_id": portfolio["portfolio_id"],
            "records": extracted_records,
        }
    )
