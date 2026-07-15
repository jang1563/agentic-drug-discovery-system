"""Command-line capture and compilation for source-pinned evidence manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .cdc_mmwr import extract_cdc_mmwr_ingestion_job
from .chembl_activity import extract_chembl_activity_ingestion_job
from .clinical_portfolio import (
    extract_clinicaltrials_gov_portfolio_job,
    normalize_clinicaltrials_gov_portfolio_job,
)
from .clinicaltrials_gov import extract_clinicaltrials_gov_ingestion_job
from .ncbi_pubmed import (
    extract_ncbi_pubmed_disease_model_ingestion_job,
    extract_ncbi_pubmed_ingestion_job,
)
from .ingestion import (
    DEFAULT_MAX_SOURCE_BYTES,
    canonical_json_bytes,
    capture_local_file,
    compile_pinned_evidence_manifest,
    fetch_https_source,
    read_source_bundle,
    write_json_artifact,
    write_source_bundle,
)


def _datetime(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("retrieved-at must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("retrieved-at must include a timezone")
    return parsed.astimezone(timezone.utc)


def _load_json(path: str | Path, label: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not readable JSON") from exc


def _capture(args: argparse.Namespace) -> dict[str, Any]:
    retrieved_at = _datetime(args.retrieved_at)
    if args.url is not None:
        if args.locator is not None:
            raise ValueError("--locator is derived from --url and must be omitted")
        bundle = fetch_https_source(
            args.url,
            receipt_id=args.receipt_id,
            source_id=args.source_id,
            source_version=args.source_version,
            retrieved_at=retrieved_at,
            timeout_seconds=args.timeout_seconds,
            max_bytes=args.max_bytes,
        )
    else:
        if args.locator is None:
            raise ValueError("--locator is required with --input-file")
        bundle = capture_local_file(
            args.input_file,
            receipt_id=args.receipt_id,
            source_id=args.source_id,
            source_version=args.source_version,
            locator=args.locator,
            retrieved_at=retrieved_at,
            media_type=args.media_type,
            max_bytes=args.max_bytes,
        )
    output = write_source_bundle(args.output, bundle)
    return {
        "status": "captured",
        "receipt_id": bundle.receipt.receipt_id,
        "source_id": bundle.receipt.source_id,
        "source_version": bundle.receipt.source_version,
        "content_hash": bundle.receipt.content_hash,
        "byte_size": bundle.receipt.byte_size,
        "bundle": str(output),
    }


def _compile(args: argparse.Namespace) -> dict[str, Any]:
    job = _load_json(args.job, "ingestion job")
    bundles = {}
    for path in args.bundle:
        bundle = read_source_bundle(path, max_bytes=args.max_bytes)
        receipt_id = bundle.receipt.receipt_id
        if receipt_id in bundles:
            raise ValueError(f"duplicate source bundle receipt_id: {receipt_id}")
        bundles[receipt_id] = bundle
    manifest, review = compile_pinned_evidence_manifest(job, bundles)
    manifest_path = Path(args.manifest_out)
    review_path = Path(args.review_out)
    if manifest_path.resolve(strict=False) == review_path.resolve(strict=False):
        raise ValueError("manifest and review outputs must be different files")
    if not args.force:
        existing = [
            path
            for path in (manifest_path, review_path)
            if path.exists() or path.is_symlink()
        ]
        if existing:
            raise ValueError(
                "compile outputs already exist: "
                + ", ".join(path.name for path in existing)
            )
    write_json_artifact(manifest_path, manifest, force=args.force)
    write_json_artifact(review_path, review, force=args.force)
    return {
        "status": "compiled_requires_human_review",
        "job_id": review["job_id"],
        "manifest": str(manifest_path),
        "review": str(review_path),
        "manifest_sha256": review["manifest_sha256"],
        "record_count": review["record_count"],
        "receipt_count": review["receipt_count"],
        "independent_source_count": review["independent_source_count"],
        "warnings": review["warnings"],
    }


def _extract_cdc_mmwr(args: argparse.Namespace) -> dict[str, Any]:
    job = _load_json(args.job, "CDC MMWR ingestion job")
    bundle = read_source_bundle(args.bundle, max_bytes=args.max_bytes)
    extracted = extract_cdc_mmwr_ingestion_job(job, bundle)
    output = write_json_artifact(args.output, extracted, force=args.force)
    return {
        "status": "provider_job_extracted_requires_human_review",
        "provider_id": "cdc_mmwr",
        "job_id": extracted["job_id"],
        "source_receipt_id": bundle.receipt.receipt_id,
        "source_content_hash": bundle.receipt.content_hash,
        "record_count": len(extracted["records"]),
        "output": str(output),
        "output_sha256": hashlib.sha256(canonical_json_bytes(extracted)).hexdigest(),
    }


def _extract_ncbi_pubmed(args: argparse.Namespace) -> dict[str, Any]:
    job = _load_json(args.job, "NCBI PubMed ingestion job")
    bundle = read_source_bundle(args.bundle, max_bytes=args.max_bytes)
    extracted = extract_ncbi_pubmed_ingestion_job(job, bundle)
    output = write_json_artifact(args.output, extracted, force=args.force)
    return {
        "status": "provider_job_extracted_requires_human_review",
        "provider_id": "ncbi_pubmed",
        "job_id": extracted["job_id"],
        "source_receipt_id": bundle.receipt.receipt_id,
        "source_content_hash": bundle.receipt.content_hash,
        "record_count": len(extracted["records"]),
        "output": str(output),
        "output_sha256": hashlib.sha256(canonical_json_bytes(extracted)).hexdigest(),
    }


def _extract_ncbi_pubmed_disease_model(
    args: argparse.Namespace,
) -> dict[str, Any]:
    job = _load_json(args.job, "NCBI PubMed disease-model ingestion job")
    bundle = read_source_bundle(args.bundle, max_bytes=args.max_bytes)
    extracted = extract_ncbi_pubmed_disease_model_ingestion_job(job, bundle)
    output = write_json_artifact(args.output, extracted, force=args.force)
    return {
        "status": "provider_job_extracted_requires_human_review",
        "provider_id": "ncbi_pubmed",
        "evidence_type": "disease_model_effect",
        "job_id": extracted["job_id"],
        "source_receipt_id": bundle.receipt.receipt_id,
        "source_content_hash": bundle.receipt.content_hash,
        "record_count": len(extracted["records"]),
        "output": str(output),
        "output_sha256": hashlib.sha256(canonical_json_bytes(extracted)).hexdigest(),
    }


def _extract_chembl_activity(args: argparse.Namespace) -> dict[str, Any]:
    job = _load_json(args.job, "ChEMBL activity ingestion job")
    receipt_ids = job.get("source_receipt_ids")
    if not isinstance(receipt_ids, dict):
        raise ValueError("ChEMBL activity job must declare source_receipt_ids")
    resource_by_receipt = {
        receipt_id: resource for resource, receipt_id in receipt_ids.items()
    }
    if len(resource_by_receipt) != len(receipt_ids):
        raise ValueError("ChEMBL activity source_receipt_ids must be unique")
    bundles = {}
    for path in args.bundle:
        bundle = read_source_bundle(path, max_bytes=args.max_bytes)
        resource = resource_by_receipt.get(bundle.receipt.receipt_id)
        if resource is None:
            raise ValueError(
                f"unexpected ChEMBL source receipt: {bundle.receipt.receipt_id}"
            )
        if resource in bundles:
            raise ValueError(f"duplicate ChEMBL source resource: {resource}")
        bundles[resource] = bundle
    extracted = extract_chembl_activity_ingestion_job(job, bundles)
    output = write_json_artifact(args.output, extracted, force=args.force)
    return {
        "status": "provider_job_extracted_requires_human_review",
        "provider_id": "chembl",
        "job_id": extracted["job_id"],
        "source_receipt_ids": {
            resource: bundle.receipt.receipt_id
            for resource, bundle in sorted(bundles.items())
        },
        "source_content_hashes": {
            resource: bundle.receipt.content_hash
            for resource, bundle in sorted(bundles.items())
        },
        "record_count": len(extracted["records"]),
        "output": str(output),
        "output_sha256": hashlib.sha256(canonical_json_bytes(extracted)).hexdigest(),
    }


def _extract_clinicaltrials_gov(args: argparse.Namespace) -> dict[str, Any]:
    job = _load_json(args.job, "ClinicalTrials.gov ingestion job")
    bundle = read_source_bundle(args.bundle, max_bytes=args.max_bytes)
    extracted = extract_clinicaltrials_gov_ingestion_job(job, bundle)
    output = write_json_artifact(args.output, extracted, force=args.force)
    return {
        "status": "provider_job_extracted_requires_human_review",
        "provider_id": "clinicaltrials_gov",
        "job_id": extracted["job_id"],
        "source_receipt_id": bundle.receipt.receipt_id,
        "source_content_hash": bundle.receipt.content_hash,
        "record_count": len(extracted["records"]),
        "output": str(output),
        "output_sha256": hashlib.sha256(canonical_json_bytes(extracted)).hexdigest(),
    }


def _extract_clinicaltrials_gov_portfolio(
    args: argparse.Namespace,
) -> dict[str, Any]:
    portfolio = _load_json(args.job, "ClinicalTrials.gov portfolio job")
    normalized_portfolio = normalize_clinicaltrials_gov_portfolio_job(portfolio)
    trial_jobs = [
        _load_json(path, "ClinicalTrials.gov trial ingestion job")
        for path in args.trial_job
    ]
    bundles = {}
    for path in args.bundle:
        bundle = read_source_bundle(path, max_bytes=args.max_bytes)
        receipt_id = bundle.receipt.receipt_id
        if receipt_id in bundles:
            raise ValueError(f"duplicate source receipt: {receipt_id}")
        bundles[receipt_id] = bundle
    extracted = extract_clinicaltrials_gov_portfolio_job(
        normalized_portfolio,
        trial_jobs,
        bundles,
    )
    output = write_json_artifact(args.output, extracted, force=args.force)
    mapping = normalized_portfolio["endpoint_mapping"]
    return {
        "status": "provider_portfolio_extracted_requires_human_review",
        "provider_id": "clinicaltrials_gov",
        "portfolio_id": normalized_portfolio["portfolio_id"],
        "endpoint_mapping_id": mapping["mapping_id"],
        "source_receipt_ids": sorted(bundles),
        "source_content_hashes": sorted(
            bundle.receipt.content_hash for bundle in bundles.values()
        ),
        "record_count": len(extracted["records"]),
        "output": str(output),
        "output_sha256": hashlib.sha256(canonical_json_bytes(extracted)).hexdigest(),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Capture exact public-source bytes outside Git and compile reviewed, "
            "payload-free pinned evidence manifests."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture = subparsers.add_parser(
        "capture",
        help="Capture one HTTPS or local source into an immutable external bundle.",
    )
    source = capture.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="Public HTTPS source URL to fetch.")
    source.add_argument(
        "--input-file", help="Existing local snapshot to hash and bundle."
    )
    capture.add_argument(
        "--locator",
        help="Public citation locator required for local-file capture.",
    )
    capture.add_argument("--receipt-id", required=True)
    capture.add_argument("--source-id", required=True)
    capture.add_argument("--source-version", required=True)
    capture.add_argument(
        "--retrieved-at",
        help="Timezone-aware ISO timestamp; defaults to the current UTC time.",
    )
    capture.add_argument("--media-type", help="Override local-file media type.")
    capture.add_argument("--timeout-seconds", type=float, default=30.0)
    capture.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_SOURCE_BYTES,
    )
    capture.add_argument(
        "--output", required=True, help="New bundle directory outside Git."
    )
    capture.set_defaults(handler=_capture)

    compile_parser = subparsers.add_parser(
        "compile",
        help="Verify source bundles and compile a manifest plus review report.",
    )
    compile_parser.add_argument("--job", required=True)
    compile_parser.add_argument(
        "--bundle",
        action="append",
        required=True,
        help="Source bundle directory; repeat once per receipt.",
    )
    compile_parser.add_argument("--manifest-out", required=True)
    compile_parser.add_argument("--review-out", required=True)
    compile_parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_SOURCE_BYTES,
    )
    compile_parser.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace existing manifest/review files.",
    )
    compile_parser.set_defaults(handler=_compile)

    mmwr = subparsers.add_parser(
        "extract-cdc-mmwr",
        help=(
            "Verify a reviewer-authored CDC MMWR extraction against captured HTML "
            "and emit a payload-free generic ingestion job."
        ),
    )
    mmwr.add_argument("--job", required=True)
    mmwr.add_argument("--bundle", required=True)
    mmwr.add_argument("--output", required=True)
    mmwr.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_SOURCE_BYTES,
    )
    mmwr.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace an existing extracted job.",
    )
    mmwr.set_defaults(handler=_extract_cdc_mmwr)

    pubmed = subparsers.add_parser(
        "extract-ncbi-pubmed",
        help=(
            "Verify a reviewer-authored NCBI PubMed extraction against captured "
            "XML and emit a payload-free generic ingestion job."
        ),
    )
    pubmed.add_argument("--job", required=True)
    pubmed.add_argument("--bundle", required=True)
    pubmed.add_argument("--output", required=True)
    pubmed.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_SOURCE_BYTES,
    )
    pubmed.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace an existing extracted job.",
    )
    pubmed.set_defaults(handler=_extract_ncbi_pubmed)

    disease_model = subparsers.add_parser(
        "extract-ncbi-pubmed-disease-model",
        help=(
            "Verify a typed in-vivo disease-model result against one captured "
            "NCBI PubMed XML record."
        ),
    )
    disease_model.add_argument("--job", required=True)
    disease_model.add_argument("--bundle", required=True)
    disease_model.add_argument("--output", required=True)
    disease_model.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_SOURCE_BYTES,
    )
    disease_model.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace an existing extracted job.",
    )
    disease_model.set_defaults(handler=_extract_ncbi_pubmed_disease_model)

    chembl = subparsers.add_parser(
        "extract-chembl-activity",
        help=(
            "Verify reviewer-authored functional activity against one ChEMBL "
            "status/activity/assay/document/molecule/target bundle."
        ),
    )
    chembl.add_argument("--job", required=True)
    chembl.add_argument(
        "--bundle",
        action="append",
        required=True,
        help="ChEMBL source bundle directory; repeat for all six job receipts.",
    )
    chembl.add_argument("--output", required=True)
    chembl.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_SOURCE_BYTES,
    )
    chembl.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace an existing extracted job.",
    )
    chembl.set_defaults(handler=_extract_chembl_activity)

    clinical = subparsers.add_parser(
        "extract-clinicaltrials-gov",
        help=(
            "Verify one posted primary endpoint, serious-adverse-event summary, "
            "population, and selected arm pair against an exact ClinicalTrials.gov "
            "study snapshot."
        ),
    )
    clinical.add_argument("--job", required=True)
    clinical.add_argument("--bundle", required=True)
    clinical.add_argument("--output", required=True)
    clinical.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_SOURCE_BYTES,
    )
    clinical.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace an existing extracted job.",
    )
    clinical.set_defaults(handler=_extract_clinicaltrials_gov)

    portfolio = subparsers.add_parser(
        "extract-clinicaltrials-gov-portfolio",
        help=(
            "Verify multiple declared ClinicalTrials.gov jobs and source bundles as "
            "one source-disjoint endpoint-mapping portfolio."
        ),
    )
    portfolio.add_argument("--job", required=True)
    portfolio.add_argument(
        "--trial-job",
        action="append",
        required=True,
        help="Single-trial review job; repeat once per portfolio trial.",
    )
    portfolio.add_argument(
        "--bundle",
        action="append",
        required=True,
        help="ClinicalTrials.gov source bundle; repeat once per portfolio trial.",
    )
    portfolio.add_argument("--output", required=True)
    portfolio.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_SOURCE_BYTES,
    )
    portfolio.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace an existing extracted portfolio job.",
    )
    portfolio.set_defaults(handler=_extract_clinicaltrials_gov_portfolio)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = args.handler(args)
    except (OSError, TypeError, ValueError, urllib.error.URLError) as exc:
        print(
            json.dumps(
                {
                    "error": {
                        "code": "pinned_ingestion_failed",
                        "message": str(exc),
                    }
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
