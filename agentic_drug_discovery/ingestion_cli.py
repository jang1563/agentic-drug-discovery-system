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
from .clinical_disposition import extract_clinical_disposition_ingestion_job
from .clinicaltrials_gov import extract_clinicaltrials_gov_ingestion_job
from .clinicaltrials_gov_inventory import (
    clinicaltrials_gov_inventory_packet_envelope,
    clinicaltrials_gov_inventory_packet_from_json,
    clinicaltrials_gov_inventory_spec_from_json,
    clinicaltrials_gov_inventory_summary,
    compile_clinicaltrials_gov_inventory,
)
from .clinicaltrials_gov_harmonization_candidates import (
    clinicaltrials_gov_harmonization_packet_envelope,
    clinicaltrials_gov_harmonization_packet_from_json,
    clinicaltrials_gov_harmonization_spec_from_json,
    clinicaltrials_gov_harmonization_summary,
    compile_clinicaltrials_gov_harmonization_candidates,
)
from .clinicaltrials_gov_harmonization_diagnostics import (
    clinicaltrials_gov_harmonization_diagnostic_report_envelope,
    clinicaltrials_gov_harmonization_diagnostic_report_from_json,
    clinicaltrials_gov_harmonization_diagnostic_spec_from_json,
    clinicaltrials_gov_harmonization_diagnostic_summary,
    compile_clinicaltrials_gov_harmonization_diagnostic,
)
from .clinicaltrials_gov_harmonization_robustness import (
    clinicaltrials_gov_harmonization_robustness_report_envelope,
    clinicaltrials_gov_harmonization_robustness_spec_from_json,
    clinicaltrials_gov_harmonization_robustness_summary,
    compile_clinicaltrials_gov_harmonization_robustness,
)
from .clinicaltrials_gov_harmonization_structure import (
    clinicaltrials_gov_harmonization_structure_report_envelope,
    clinicaltrials_gov_harmonization_structure_report_from_json,
    clinicaltrials_gov_harmonization_structure_spec_from_json,
    clinicaltrials_gov_harmonization_structure_summary,
    compile_clinicaltrials_gov_harmonization_structure,
)
from .clinicaltrials_gov_structural_presence import (
    clinicaltrials_gov_harmonization_presence_report_envelope,
    clinicaltrials_gov_harmonization_presence_spec_from_json,
    clinicaltrials_gov_harmonization_presence_summary,
    clinicaltrials_gov_structural_presence_packet_envelope,
    clinicaltrials_gov_structural_presence_packet_from_json,
    clinicaltrials_gov_structural_presence_spec_from_json,
    clinicaltrials_gov_structural_presence_summary,
    compile_clinicaltrials_gov_harmonization_presence,
    compile_clinicaltrials_gov_structural_presence,
)
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


def _extract_clinicaltrials_gov_inventory(
    args: argparse.Namespace,
) -> dict[str, Any]:
    try:
        spec_text = Path(args.spec).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError("ClinicalTrials.gov inventory spec is unreadable") from exc
    spec = clinicaltrials_gov_inventory_spec_from_json(spec_text)
    bundle = read_source_bundle(args.bundle, max_bytes=args.max_bytes)
    packet = compile_clinicaltrials_gov_inventory(spec, bundle)
    envelope = clinicaltrials_gov_inventory_packet_envelope(packet)
    output = write_json_artifact(args.output, envelope, force=args.force)
    return {
        "status": "registry_inventory_compiled",
        **clinicaltrials_gov_inventory_summary(packet),
        "source_content_hash": bundle.receipt.content_hash,
        "output": str(output),
        "output_sha256": hashlib.sha256(canonical_json_bytes(envelope)).hexdigest(),
    }


def _compile_clinicaltrials_gov_structural_presence(
    args: argparse.Namespace,
) -> dict[str, Any]:
    try:
        spec_text = Path(args.spec).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(
            "ClinicalTrials.gov structural presence spec is unreadable"
        ) from exc
    spec = clinicaltrials_gov_structural_presence_spec_from_json(spec_text)
    if args.max_bytes <= 0:
        raise ValueError("max-bytes must be positive")
    bundle = read_source_bundle(args.bundle, max_bytes=args.max_bytes)
    try:
        inventory_bytes = Path(args.inventory).read_bytes()
    except OSError as exc:
        raise ValueError("ClinicalTrials.gov inventory packet is unreadable") from exc
    if len(inventory_bytes) > args.max_bytes:
        raise ValueError("ClinicalTrials.gov inventory packet exceeds max-bytes")
    try:
        inventory_text = inventory_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("ClinicalTrials.gov inventory packet is not UTF-8") from exc
    inventory = clinicaltrials_gov_inventory_packet_from_json(inventory_text)
    packet = compile_clinicaltrials_gov_structural_presence(spec, bundle, inventory)
    envelope = clinicaltrials_gov_structural_presence_packet_envelope(packet)
    output = write_json_artifact(args.output, envelope, force=args.force)
    return {
        "status": "clinicaltrials_gov_structural_presence_compiled",
        **clinicaltrials_gov_structural_presence_summary(packet),
        "output": str(output),
        "output_sha256": hashlib.sha256(canonical_json_bytes(envelope)).hexdigest(),
    }


def _compile_clinicaltrials_gov_harmonization_candidates(
    args: argparse.Namespace,
) -> dict[str, Any]:
    try:
        spec_text = Path(args.spec).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError("ClinicalTrials.gov harmonization spec is unreadable") from exc
    spec = clinicaltrials_gov_harmonization_spec_from_json(spec_text)
    inventories = []
    if args.max_bytes <= 0:
        raise ValueError("max-bytes must be positive")
    total_bytes = 0
    for path in args.inventory:
        try:
            inventory_bytes = Path(path).read_bytes()
        except OSError as exc:
            raise ValueError(
                f"ClinicalTrials.gov inventory packet is unreadable: {path}"
            ) from exc
        total_bytes += len(inventory_bytes)
        if total_bytes > args.max_bytes:
            raise ValueError(
                "ClinicalTrials.gov inventory packet bytes exceed max-bytes"
            )
        try:
            inventory_text = inventory_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"ClinicalTrials.gov inventory packet is not UTF-8: {path}"
            ) from exc
        inventories.append(
            clinicaltrials_gov_inventory_packet_from_json(inventory_text)
        )
    packet = compile_clinicaltrials_gov_harmonization_candidates(spec, inventories)
    envelope = clinicaltrials_gov_harmonization_packet_envelope(packet)
    output = write_json_artifact(args.output, envelope, force=args.force)
    return {
        "status": "cross_trial_harmonization_candidates_compiled",
        **clinicaltrials_gov_harmonization_summary(packet),
        "output": str(output),
        "output_sha256": hashlib.sha256(canonical_json_bytes(envelope)).hexdigest(),
    }


def _diagnose_clinicaltrials_gov_harmonization(
    args: argparse.Namespace,
) -> dict[str, Any]:
    try:
        spec_text = Path(args.spec).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(
            "ClinicalTrials.gov harmonization diagnostic spec is unreadable"
        ) from exc
    spec = clinicaltrials_gov_harmonization_diagnostic_spec_from_json(spec_text)
    if args.max_bytes <= 0:
        raise ValueError("max-bytes must be positive")
    try:
        packet_bytes = Path(args.candidate_packet).read_bytes()
    except OSError as exc:
        raise ValueError("harmonization candidate packet is unreadable") from exc
    if len(packet_bytes) > args.max_bytes:
        raise ValueError("harmonization candidate packet exceeds max-bytes")
    try:
        packet_text = packet_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("harmonization candidate packet is not UTF-8") from exc
    candidate_packet = clinicaltrials_gov_harmonization_packet_from_json(packet_text)
    report = compile_clinicaltrials_gov_harmonization_diagnostic(spec, candidate_packet)
    envelope = clinicaltrials_gov_harmonization_diagnostic_report_envelope(report)
    output = write_json_artifact(args.output, envelope, force=args.force)
    return {
        "status": "cross_trial_harmonization_diagnostic_compiled",
        **clinicaltrials_gov_harmonization_diagnostic_summary(report),
        "output": str(output),
        "output_sha256": hashlib.sha256(canonical_json_bytes(envelope)).hexdigest(),
    }


def _benchmark_clinicaltrials_gov_harmonization_robustness(
    args: argparse.Namespace,
) -> dict[str, Any]:
    try:
        spec_text = Path(args.spec).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(
            "ClinicalTrials.gov harmonization robustness spec is unreadable"
        ) from exc
    spec = clinicaltrials_gov_harmonization_robustness_spec_from_json(spec_text)
    if args.max_bytes <= 0:
        raise ValueError("max-bytes must be positive")
    reports = []
    total_bytes = 0
    for path in args.diagnostic_report:
        try:
            report_bytes = Path(path).read_bytes()
        except OSError as exc:
            raise ValueError(
                f"harmonization diagnostic report is unreadable: {path}"
            ) from exc
        total_bytes += len(report_bytes)
        if total_bytes > args.max_bytes:
            raise ValueError("harmonization diagnostic reports exceed max-bytes")
        try:
            report_text = report_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"harmonization diagnostic report is not UTF-8: {path}"
            ) from exc
        reports.append(
            clinicaltrials_gov_harmonization_diagnostic_report_from_json(report_text)
        )
    report = compile_clinicaltrials_gov_harmonization_robustness(spec, reports)
    envelope = clinicaltrials_gov_harmonization_robustness_report_envelope(report)
    output = write_json_artifact(args.output, envelope, force=args.force)
    return {
        "status": "cross_cohort_harmonization_robustness_compiled",
        **clinicaltrials_gov_harmonization_robustness_summary(report),
        "output": str(output),
        "output_sha256": hashlib.sha256(canonical_json_bytes(envelope)).hexdigest(),
    }


def _decompose_clinicaltrials_gov_harmonization_structure(
    args: argparse.Namespace,
) -> dict[str, Any]:
    try:
        spec_text = Path(args.spec).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(
            "ClinicalTrials.gov harmonization structure spec is unreadable"
        ) from exc
    spec = clinicaltrials_gov_harmonization_structure_spec_from_json(spec_text)
    if args.max_bytes <= 0:
        raise ValueError("max-bytes must be positive")
    inputs = []
    total_bytes = 0
    for path, label, parser in (
        (
            args.candidate_packet,
            "harmonization candidate packet",
            clinicaltrials_gov_harmonization_packet_from_json,
        ),
        (
            args.diagnostic_report,
            "harmonization diagnostic report",
            clinicaltrials_gov_harmonization_diagnostic_report_from_json,
        ),
    ):
        try:
            payload = Path(path).read_bytes()
        except OSError as exc:
            raise ValueError(f"{label} is unreadable") from exc
        total_bytes += len(payload)
        if total_bytes > args.max_bytes:
            raise ValueError("harmonization structure inputs exceed max-bytes")
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"{label} is not UTF-8") from exc
        inputs.append(parser(text))
    candidate_packet, diagnostic_report = inputs
    report = compile_clinicaltrials_gov_harmonization_structure(
        spec, candidate_packet, diagnostic_report
    )
    envelope = clinicaltrials_gov_harmonization_structure_report_envelope(report)
    output = write_json_artifact(args.output, envelope, force=args.force)
    return {
        "status": "cross_trial_harmonization_structure_decomposed",
        **clinicaltrials_gov_harmonization_structure_summary(report),
        "output": str(output),
        "output_sha256": hashlib.sha256(canonical_json_bytes(envelope)).hexdigest(),
    }


def _resolve_clinicaltrials_gov_harmonization_presence(
    args: argparse.Namespace,
) -> dict[str, Any]:
    try:
        spec_text = Path(args.spec).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(
            "ClinicalTrials.gov harmonization presence spec is unreadable"
        ) from exc
    spec = clinicaltrials_gov_harmonization_presence_spec_from_json(spec_text)
    if args.max_bytes <= 0:
        raise ValueError("max-bytes must be positive")
    inputs = []
    total_bytes = 0
    input_specs = (
        (
            args.candidate_packet,
            "harmonization candidate packet",
            clinicaltrials_gov_harmonization_packet_from_json,
        ),
        (
            args.structure_report,
            "harmonization structure report",
            clinicaltrials_gov_harmonization_structure_report_from_json,
        ),
        *(
            (
                path,
                f"structural presence sidecar {path}",
                clinicaltrials_gov_structural_presence_packet_from_json,
            )
            for path in args.sidecar
        ),
    )
    for path, label, parser in input_specs:
        try:
            payload = Path(path).read_bytes()
        except OSError as exc:
            raise ValueError(f"{label} is unreadable") from exc
        total_bytes += len(payload)
        if total_bytes > args.max_bytes:
            raise ValueError("harmonization presence inputs exceed max-bytes")
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"{label} is not UTF-8") from exc
        inputs.append(parser(text))
    candidate_packet, structure_report, *sidecars = inputs
    report = compile_clinicaltrials_gov_harmonization_presence(
        spec, candidate_packet, structure_report, sidecars
    )
    envelope = clinicaltrials_gov_harmonization_presence_report_envelope(report)
    output = write_json_artifact(args.output, envelope, force=args.force)
    return {
        "status": "cross_trial_harmonization_source_presence_resolved",
        **clinicaltrials_gov_harmonization_presence_summary(report),
        "output": str(output),
        "output_sha256": hashlib.sha256(canonical_json_bytes(envelope)).hexdigest(),
    }


def _extract_clinical_trial_disposition(
    args: argparse.Namespace,
) -> dict[str, Any]:
    job = _load_json(args.job, "clinical trial disposition ingestion job")
    bundles = {
        "registry": read_source_bundle(args.registry_bundle, max_bytes=args.max_bytes),
        "publication": read_source_bundle(
            args.publication_bundle, max_bytes=args.max_bytes
        ),
    }
    extracted = extract_clinical_disposition_ingestion_job(job, bundles)
    output = write_json_artifact(args.output, extracted, force=args.force)
    return {
        "status": "provider_job_extracted_requires_human_review",
        "provider_ids": ["clinicaltrials_gov", "ncbi_pubmed"],
        "job_id": extracted["job_id"],
        "source_receipt_ids": {
            role: bundle.receipt.receipt_id for role, bundle in bundles.items()
        },
        "source_content_hashes": {
            role: bundle.receipt.content_hash for role, bundle in bundles.items()
        },
        "record_count": len(extracted["records"]),
        "independent_trial_count": 1,
        "shared_trial_lineage": True,
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

    inventory = subparsers.add_parser(
        "extract-clinicaltrials-gov-inventory",
        help=(
            "Enumerate every protocol outcome, posted outcome, and adverse-event "
            "record in one exact ClinicalTrials.gov study snapshot without "
            "semantic approval."
        ),
    )
    inventory.add_argument("--spec", required=True)
    inventory.add_argument("--bundle", required=True)
    inventory.add_argument("--output", required=True)
    inventory.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_SOURCE_BYTES,
    )
    inventory.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace an existing inventory packet.",
    )
    inventory.set_defaults(handler=_extract_clinicaltrials_gov_inventory)

    structural_presence = subparsers.add_parser(
        "compile-clinicaltrials-gov-structural-presence",
        help=(
            "Replay an immutable registry inventory from its exact source bundle "
            "and preserve absent, null, empty, and non-empty structural-array "
            "states without retaining array values."
        ),
    )
    structural_presence.add_argument("--spec", required=True)
    structural_presence.add_argument("--bundle", required=True)
    structural_presence.add_argument("--inventory", required=True)
    structural_presence.add_argument("--output", required=True)
    structural_presence.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_SOURCE_BYTES,
    )
    structural_presence.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace an existing structural presence sidecar.",
    )
    structural_presence.set_defaults(
        handler=_compile_clinicaltrials_gov_structural_presence
    )

    harmonization = subparsers.add_parser(
        "compile-clinicaltrials-gov-harmonization-candidates",
        help=(
            "Enumerate every posted-outcome pair across exact ClinicalTrials.gov "
            "inventory packets while retaining trial-level safety provenance and "
            "without semantic approval."
        ),
    )
    harmonization.add_argument("--spec", required=True)
    harmonization.add_argument(
        "--inventory",
        action="append",
        required=True,
        help="Exact registry inventory packet; repeat once per trial.",
    )
    harmonization.add_argument("--output", required=True)
    harmonization.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_SOURCE_BYTES,
        help="Maximum total bytes across all input inventory packets.",
    )
    harmonization.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace an existing harmonization candidate packet.",
    )
    harmonization.set_defaults(
        handler=_compile_clinicaltrials_gov_harmonization_candidates
    )

    harmonization_diagnostic = subparsers.add_parser(
        "diagnose-clinicaltrials-gov-harmonization",
        help=(
            "Aggregate cross-trial endpoint and safety review blockers without "
            "retaining endpoint titles, pair identities, safety terms, or approval."
        ),
    )
    harmonization_diagnostic.add_argument("--spec", required=True)
    harmonization_diagnostic.add_argument("--candidate-packet", required=True)
    harmonization_diagnostic.add_argument("--output", required=True)
    harmonization_diagnostic.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_SOURCE_BYTES,
    )
    harmonization_diagnostic.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace an existing harmonization diagnostic report.",
    )
    harmonization_diagnostic.set_defaults(
        handler=_diagnose_clinicaltrials_gov_harmonization
    )

    harmonization_robustness = subparsers.add_parser(
        "benchmark-clinicaltrials-gov-harmonization-robustness",
        help=(
            "Compare exact per-cohort harmonization diagnostic rates without "
            "pooling, weighting, ranking, or semantic inference."
        ),
    )
    harmonization_robustness.add_argument("--spec", required=True)
    harmonization_robustness.add_argument(
        "--diagnostic-report",
        action="append",
        required=True,
        help="Exact payload-free diagnostic report; repeat once per cohort.",
    )
    harmonization_robustness.add_argument("--output", required=True)
    harmonization_robustness.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_SOURCE_BYTES,
    )
    harmonization_robustness.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace an existing harmonization robustness report.",
    )
    harmonization_robustness.set_defaults(
        handler=_benchmark_clinicaltrials_gov_harmonization_robustness
    )

    harmonization_structure = subparsers.add_parser(
        "decompose-clinicaltrials-gov-harmonization-structure",
        help=(
            "Partition structural endpoint disagreement into trial-global and "
            "endpoint-local causes without retaining structural values or "
            "inferring endpoint equivalence."
        ),
    )
    harmonization_structure.add_argument("--spec", required=True)
    harmonization_structure.add_argument("--candidate-packet", required=True)
    harmonization_structure.add_argument("--diagnostic-report", required=True)
    harmonization_structure.add_argument("--output", required=True)
    harmonization_structure.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_SOURCE_BYTES,
        help="Maximum total bytes across packet and diagnostic inputs.",
    )
    harmonization_structure.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace an existing structure report.",
    )
    harmonization_structure.set_defaults(
        handler=_decompose_clinicaltrials_gov_harmonization_structure
    )

    harmonization_presence = subparsers.add_parser(
        "resolve-clinicaltrials-gov-harmonization-presence",
        help=(
            "Resolve legacy zero-versus-missing structural ambiguity against "
            "exact source-bound sidecars without publishing source arrays."
        ),
    )
    harmonization_presence.add_argument("--spec", required=True)
    harmonization_presence.add_argument("--candidate-packet", required=True)
    harmonization_presence.add_argument("--structure-report", required=True)
    harmonization_presence.add_argument(
        "--sidecar",
        action="append",
        required=True,
        help="Exact structural presence sidecar; repeat once per trial.",
    )
    harmonization_presence.add_argument("--output", required=True)
    harmonization_presence.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_SOURCE_BYTES,
        help="Maximum total bytes across packet, report, and sidecars.",
    )
    harmonization_presence.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace an existing presence resolution report.",
    )
    harmonization_presence.set_defaults(
        handler=_resolve_clinicaltrials_gov_harmonization_presence
    )

    disposition = subparsers.add_parser(
        "extract-clinical-trial-disposition",
        help=(
            "Verify one terminated ClinicalTrials.gov record and one PubMed "
            "primary-endpoint result bound to the same trial lineage."
        ),
    )
    disposition.add_argument("--job", required=True)
    disposition.add_argument("--registry-bundle", required=True)
    disposition.add_argument("--publication-bundle", required=True)
    disposition.add_argument("--output", required=True)
    disposition.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_SOURCE_BYTES,
    )
    disposition.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace an existing extracted job.",
    )
    disposition.set_defaults(handler=_extract_clinical_trial_disposition)

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
