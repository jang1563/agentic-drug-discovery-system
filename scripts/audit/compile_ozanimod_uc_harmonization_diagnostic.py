#!/usr/bin/env python3
"""Replay the exact ozanimod UC harmonization difficulty diagnostic."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from agentic_drug_discovery.clinicaltrials_gov_harmonization_candidates import (
    ClinicalTrialsGovHarmonizationCandidateSpec,
    ClinicalTrialsGovHarmonizationInventoryBinding,
    compile_clinicaltrials_gov_harmonization_candidates,
    validate_clinicaltrials_gov_harmonization_candidates,
)
from agentic_drug_discovery.clinicaltrials_gov_harmonization_diagnostics import (
    ClinicalTrialsGovHarmonizationDiagnosticSpec,
    clinicaltrials_gov_harmonization_diagnostic_report_envelope,
    clinicaltrials_gov_harmonization_diagnostic_spec_to_dict,
    clinicaltrials_gov_harmonization_diagnostic_summary,
    compile_clinicaltrials_gov_harmonization_diagnostic,
    validate_clinicaltrials_gov_harmonization_diagnostic,
)
from agentic_drug_discovery.clinicaltrials_gov_inventory import (
    ClinicalTrialsGovInventorySpec,
    compile_clinicaltrials_gov_inventory,
    validate_clinicaltrials_gov_inventory,
)
from agentic_drug_discovery.ingestion import capture_source_bytes, write_json_artifact


REGISTRY_VERSION = "2026-08-25"
DEFAULT_RETRIEVED_AT = "2026-08-25T18:17:01+00:00"
SOURCE_HASHES = {
    "NCT01647516": "71ed6feb2d11e4c8d8cd82ca1bbfa7baf619d0b2f403763d38bfadeed07c4d89",
    "NCT02435992": "5cfb559f2b89bfefa4004b8a8ab7ca5561389a882ff70f205fda5ce34d3faf07",
}


def _retrieved_at(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "retrieved-at must be an ISO timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("retrieved-at must include a UTC offset")
    return parsed


def _inventory(nct_id: str, source_path: Path, retrieved_at: datetime):
    payload = source_path.read_bytes()
    observed_hash = hashlib.sha256(payload).hexdigest()
    if observed_hash != SOURCE_HASHES[nct_id]:
        raise ValueError(
            f"{nct_id} source SHA-256 mismatch: expected {SOURCE_HASHES[nct_id]}, "
            f"observed {observed_hash}"
        )
    receipt_id = f"ctgov-{nct_id.lower()}-{REGISTRY_VERSION}"
    bundle = capture_source_bytes(
        payload,
        receipt_id=receipt_id,
        source_id=f"clinicaltrials-gov-{nct_id}",
        source_version=f"clinicaltrials-gov-{nct_id}-version-{REGISTRY_VERSION}",
        locator=f"https://clinicaltrials.gov/api/v2/studies/{nct_id}",
        retrieved_at=retrieved_at,
        media_type="application/json",
        capture_method="https",
        http_status=200,
    )
    spec = ClinicalTrialsGovInventorySpec(
        inventory_id=f"{nct_id}:registry-record-wide-inventory:{REGISTRY_VERSION}",
        source_receipt_id=receipt_id,
        nct_id=nct_id,
        registry_version=REGISTRY_VERSION,
    )
    packet = compile_clinicaltrials_gov_inventory(spec, bundle)
    failures = validate_clinicaltrials_gov_inventory(spec, bundle, packet)
    if failures:
        raise ValueError(f"{nct_id} inventory replay failed: {failures}")
    return packet


def compile_report(
    nct01647516_source: Path,
    nct02435992_source: Path,
    retrieved_at: datetime,
):
    packets = tuple(
        sorted(
            (
                _inventory("NCT01647516", nct01647516_source, retrieved_at),
                _inventory("NCT02435992", nct02435992_source, retrieved_at),
            ),
            key=lambda item: item.nct_id,
        )
    )
    candidate_spec = ClinicalTrialsGovHarmonizationCandidateSpec(
        packet_id=f"ozanimod-uc-cross-trial-candidates:{REGISTRY_VERSION}",
        inventory_bindings=tuple(
            ClinicalTrialsGovHarmonizationInventoryBinding(
                inventory_id=packet.inventory_id,
                nct_id=packet.nct_id,
                inventory_sha256=packet.fingerprint,
            )
            for packet in packets
        ),
        max_endpoint_candidate_count=100,
        max_pair_count=5000,
    )
    candidate_packet = compile_clinicaltrials_gov_harmonization_candidates(
        candidate_spec, tuple(reversed(packets))
    )
    candidate_failures = validate_clinicaltrials_gov_harmonization_candidates(
        candidate_spec, packets, candidate_packet
    )
    if candidate_failures:
        raise ValueError(f"candidate graph replay failed: {candidate_failures}")
    diagnostic_spec = ClinicalTrialsGovHarmonizationDiagnosticSpec(
        report_id=f"ozanimod-uc-harmonization-difficulty:{REGISTRY_VERSION}",
        candidate_packet_sha256=candidate_packet.fingerprint,
    )
    report = compile_clinicaltrials_gov_harmonization_diagnostic(
        diagnostic_spec, candidate_packet
    )
    diagnostic_failures = validate_clinicaltrials_gov_harmonization_diagnostic(
        diagnostic_spec, candidate_packet, report
    )
    if diagnostic_failures:
        raise ValueError(f"diagnostic replay failed: {diagnostic_failures}")
    return diagnostic_spec, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nct01647516-source", required=True, type=Path)
    parser.add_argument("--nct02435992-source", required=True, type=Path)
    parser.add_argument(
        "--retrieved-at", default=DEFAULT_RETRIEVED_AT, type=_retrieved_at
    )
    parser.add_argument("--spec-output", required=True, type=Path)
    parser.add_argument("--report-output", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    spec, report = compile_report(
        args.nct01647516_source,
        args.nct02435992_source,
        args.retrieved_at,
    )
    write_json_artifact(
        args.spec_output,
        clinicaltrials_gov_harmonization_diagnostic_spec_to_dict(spec),
        force=args.force,
    )
    write_json_artifact(
        args.report_output,
        clinicaltrials_gov_harmonization_diagnostic_report_envelope(report),
        force=args.force,
    )
    print(json.dumps(clinicaltrials_gov_harmonization_diagnostic_summary(report)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
