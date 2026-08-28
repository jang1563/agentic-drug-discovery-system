#!/usr/bin/env python3
"""Replay exact registry and protocol/SAP bytes into estimand page cues."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from agentic_drug_discovery.clinicaltrials_gov_estimand_evidence_acquisition import (
    ClinicalTrialsGovEstimandEvidenceAcquisitionSpec,
    EstimandEvidenceDocumentBinding,
    clinicaltrials_gov_estimand_evidence_acquisition_packet_envelope,
    clinicaltrials_gov_estimand_evidence_acquisition_spec_to_dict,
    clinicaltrials_gov_estimand_evidence_acquisition_summary,
    compile_clinicaltrials_gov_estimand_evidence_acquisition,
    validate_clinicaltrials_gov_estimand_evidence_acquisition,
)
from agentic_drug_discovery.ingestion import DEFAULT_MAX_SOURCE_BYTES, write_json_artifact
from compile_clinicaltrials_gov_endpoint_estimand_preflight import (
    _assignment,
    _hash_assignment,
    _registry_version,
    _retrieved_at,
    _unique_assignments,
    compile_preflight,
)


_DOCUMENT_ID = re.compile(r"^(NCT[0-9]{8}):([^/]+\.pdf)$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _document_assignment(value: str) -> tuple[str, str]:
    try:
        key, item = value.split("=", maxsplit=1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "document must use NCT########:FILE.pdf=VALUE"
        ) from exc
    if _DOCUMENT_ID.fullmatch(key) is None or not item:
        raise argparse.ArgumentTypeError(
            "document must use NCT########:FILE.pdf=VALUE"
        )
    return key, item


def _document_hash_assignment(value: str) -> tuple[str, str]:
    document_id, digest = _document_assignment(value)
    if _SHA256.fullmatch(digest) is None:
        raise argparse.ArgumentTypeError("document hash must be lowercase SHA-256")
    return document_id, digest


def _document_bindings(
    source_paths: dict[str, str],
    document_hashes: dict[str, str],
) -> tuple[EstimandEvidenceDocumentBinding, ...]:
    bindings: list[EstimandEvidenceDocumentBinding] = []
    observed_ids: set[str] = set()
    for nct_id, source_path in sorted(source_paths.items()):
        try:
            source = json.loads(Path(source_path).read_text(encoding="utf-8"))
            documents = source["documentSection"]["largeDocumentModule"]["largeDocs"]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ValueError(f"{nct_id} large-document inventory is unavailable") from exc
        for document in documents:
            if not document.get("hasProtocol") and not document.get("hasSap"):
                continue
            filename = document.get("filename")
            document_id = f"{nct_id}:{filename}"
            try:
                digest = document_hashes[document_id]
            except KeyError as exc:
                raise ValueError(f"missing declared hash for {document_id}") from exc
            roles = tuple(
                role
                for role, field_name in (
                    ("protocol", "hasProtocol"),
                    ("sap", "hasSap"),
                )
                if document.get(field_name) is True
            )
            bindings.append(
                EstimandEvidenceDocumentBinding(
                    document_id=document_id,
                    nct_id=nct_id,
                    filename=filename,
                    document_roles=roles,
                    source_label=document["label"],
                    source_locator=(
                        "https://cdn.clinicaltrials.gov/large-docs/"
                        f"{nct_id[-2:]}/{nct_id}/{filename}"
                    ),
                    source_document_date=document["date"],
                    source_upload_date=document["uploadDate"],
                    expected_size_bytes=document["size"],
                    source_content_sha256=digest,
                )
            )
            observed_ids.add(document_id)
    if observed_ids != set(document_hashes):
        unexpected = sorted(set(document_hashes) - observed_ids)
        raise ValueError(f"document hashes include unknown inventory entries: {unexpected}")
    return tuple(sorted(bindings, key=lambda item: item.document_id))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort-id", required=True)
    parser.add_argument("--registry-version", required=True, type=_registry_version)
    parser.add_argument("--retrieved-at", required=True, type=_retrieved_at)
    parser.add_argument(
        "--registry-study",
        action="append",
        required=True,
        type=_assignment,
        metavar="NCT########=PATH",
    )
    parser.add_argument(
        "--source-sha256",
        action="append",
        required=True,
        type=_hash_assignment,
        metavar="NCT########=SHA256",
    )
    parser.add_argument(
        "--document",
        action="append",
        required=True,
        type=_document_assignment,
        metavar="NCT########:FILE.pdf=PATH",
    )
    parser.add_argument(
        "--document-sha256",
        action="append",
        required=True,
        type=_document_hash_assignment,
        metavar="NCT########:FILE.pdf=SHA256",
    )
    parser.add_argument("--output-spec", required=True, type=Path)
    parser.add_argument("--output-packet", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-source-bytes", type=int, default=DEFAULT_MAX_SOURCE_BYTES)
    parser.add_argument("--max-document-bytes", type=int, default=16 * 1024 * 1024)
    parser.add_argument("--max-endpoint-candidate-count", type=int, default=1000)
    parser.add_argument("--max-pair-count", type=int, default=10000)
    parser.add_argument("--max-structural-array-record-count", type=int, default=10000)
    parser.add_argument("--max-candidate-pages-per-dimension", type=int, default=5)
    args = parser.parse_args()

    source_paths = _unique_assignments(args.registry_study, "registry-study")
    source_hashes = _unique_assignments(args.source_sha256, "source-sha256")
    document_paths = _unique_assignments(args.document, "document")
    document_hashes = _unique_assignments(
        args.document_sha256, "document-sha256"
    )
    if set(document_paths) != set(document_hashes):
        raise ValueError("document and document-sha256 sets must match exactly")

    _preflight_spec, preflight, candidate = compile_preflight(
        cohort_id=args.cohort_id,
        registry_version=args.registry_version,
        retrieved_at=args.retrieved_at,
        source_paths=source_paths,
        source_hashes=source_hashes,
        max_source_bytes=args.max_source_bytes,
        max_endpoint_candidate_count=args.max_endpoint_candidate_count,
        max_pair_count=args.max_pair_count,
        max_structural_array_record_count=args.max_structural_array_record_count,
    )
    bindings = _document_bindings(source_paths, document_hashes)
    spec = ClinicalTrialsGovEstimandEvidenceAcquisitionSpec(
        packet_id=(
            f"{args.cohort_id}-estimand-evidence-acquisition:"
            f"{args.registry_version}"
        ),
        candidate_packet_sha256=candidate.fingerprint,
        preflight_packet_sha256=preflight.fingerprint,
        document_bindings=bindings,
        max_document_bytes=args.max_document_bytes,
        max_candidate_pages_per_dimension=args.max_candidate_pages_per_dimension,
    )
    registry_payloads = {
        nct_id: Path(path).read_bytes() for nct_id, path in source_paths.items()
    }
    document_payloads = {
        document_id: Path(path).read_bytes()
        for document_id, path in document_paths.items()
    }
    for document_id, payload in document_payloads.items():
        if hashlib.sha256(payload).hexdigest() != document_hashes[document_id]:
            raise ValueError(f"{document_id} document SHA-256 mismatch")
    packet = compile_clinicaltrials_gov_estimand_evidence_acquisition(
        spec,
        candidate,
        preflight,
        registry_payloads,
        document_payloads,
    )
    failures = validate_clinicaltrials_gov_estimand_evidence_acquisition(
        spec,
        candidate,
        preflight,
        registry_payloads,
        document_payloads,
        packet,
    )
    if failures:
        raise ValueError(f"estimand evidence-acquisition replay failed: {failures}")
    write_json_artifact(
        args.output_spec,
        clinicaltrials_gov_estimand_evidence_acquisition_spec_to_dict(spec),
        force=args.force,
    )
    write_json_artifact(
        args.output_packet,
        clinicaltrials_gov_estimand_evidence_acquisition_packet_envelope(packet),
        force=args.force,
    )
    print(
        json.dumps(
            clinicaltrials_gov_estimand_evidence_acquisition_summary(packet),
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
