#!/usr/bin/env python3
"""Replay one exact ClinicalTrials.gov cohort into endpoint/estimand preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path

from agentic_drug_discovery.clinicaltrials_gov_endpoint_estimand_preflight import (
    ClinicalTrialsGovEndpointEstimandPreflightSpec,
    clinicaltrials_gov_endpoint_estimand_preflight_packet_envelope,
    clinicaltrials_gov_endpoint_estimand_preflight_spec_to_dict,
    clinicaltrials_gov_endpoint_estimand_preflight_summary,
    compile_clinicaltrials_gov_endpoint_estimand_preflight,
    validate_clinicaltrials_gov_endpoint_estimand_preflight,
)
from agentic_drug_discovery.clinicaltrials_gov_harmonization_candidates import (
    ClinicalTrialsGovHarmonizationCandidateSpec,
    ClinicalTrialsGovHarmonizationInventoryBinding,
    compile_clinicaltrials_gov_harmonization_candidates,
    validate_clinicaltrials_gov_harmonization_candidates,
)
from agentic_drug_discovery.clinicaltrials_gov_harmonization_diagnostics import (
    ClinicalTrialsGovHarmonizationDiagnosticSpec,
    compile_clinicaltrials_gov_harmonization_diagnostic,
    validate_clinicaltrials_gov_harmonization_diagnostic,
)
from agentic_drug_discovery.clinicaltrials_gov_harmonization_structure import (
    ClinicalTrialsGovHarmonizationStructureSpec,
    compile_clinicaltrials_gov_harmonization_structure,
    validate_clinicaltrials_gov_harmonization_structure,
)
from agentic_drug_discovery.clinicaltrials_gov_inventory import (
    ClinicalTrialsGovInventorySpec,
    compile_clinicaltrials_gov_inventory,
    validate_clinicaltrials_gov_inventory,
)
from agentic_drug_discovery.clinicaltrials_gov_structural_presence import (
    ClinicalTrialsGovHarmonizationPresenceSpec,
    ClinicalTrialsGovStructuralPresenceSpec,
    StructuralPresenceSidecarBinding,
    compile_clinicaltrials_gov_harmonization_presence,
    compile_clinicaltrials_gov_structural_presence,
    validate_clinicaltrials_gov_harmonization_presence,
    validate_clinicaltrials_gov_structural_presence,
)
from agentic_drug_discovery.ingestion import (
    DEFAULT_MAX_SOURCE_BYTES,
    capture_source_bytes,
    write_json_artifact,
)


_NCT_ID = re.compile(r"^NCT[0-9]{8}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _assignment(value: str) -> tuple[str, str]:
    try:
        key, item = value.split("=", maxsplit=1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must use NCT########=VALUE") from exc
    if _NCT_ID.fullmatch(key) is None or not item:
        raise argparse.ArgumentTypeError("value must use NCT########=VALUE")
    return key, item


def _hash_assignment(value: str) -> tuple[str, str]:
    nct_id, digest = _assignment(value)
    if _SHA256.fullmatch(digest) is None:
        raise argparse.ArgumentTypeError("source hash must be lowercase SHA-256")
    return nct_id, digest


def _registry_version(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "registry-version must use YYYY-MM-DD"
        ) from exc
    if parsed.isoformat() != value:
        raise argparse.ArgumentTypeError("registry-version must use YYYY-MM-DD")
    return value


def _retrieved_at(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "retrieved-at must be an ISO timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("retrieved-at must include a UTC offset")
    return parsed


def _unique_assignments(
    values: list[tuple[str, str]], label: str
) -> dict[str, str]:
    result: dict[str, str] = {}
    for nct_id, value in values:
        if nct_id in result:
            raise ValueError(f"duplicate {label} NCT id: {nct_id}")
        result[nct_id] = value
    return result


def _inventory(
    nct_id: str,
    source_path: Path,
    expected_sha256: str,
    registry_version: str,
    retrieved_at: datetime,
    max_source_bytes: int,
):
    with source_path.open("rb") as handle:
        payload = handle.read(max_source_bytes + 1)
    if len(payload) > max_source_bytes:
        raise ValueError(
            f"{nct_id} source exceeds max-source-bytes ({max_source_bytes})"
        )
    observed_hash = hashlib.sha256(payload).hexdigest()
    if observed_hash != expected_sha256:
        raise ValueError(
            f"{nct_id} source SHA-256 mismatch: expected {expected_sha256}, "
            f"observed {observed_hash}"
        )
    receipt_id = f"ctgov-{nct_id.lower()}-{registry_version}"
    bundle = capture_source_bytes(
        payload,
        receipt_id=receipt_id,
        source_id=f"clinicaltrials-gov-{nct_id}",
        source_version=(
            f"clinicaltrials-gov-{nct_id}-version-{registry_version}"
        ),
        locator=f"https://clinicaltrials.gov/api/v2/studies/{nct_id}",
        retrieved_at=retrieved_at,
        media_type="application/json",
        capture_method="https",
        http_status=200,
    )
    spec = ClinicalTrialsGovInventorySpec(
        inventory_id=f"{nct_id}:registry-record-wide-inventory:{registry_version}",
        source_receipt_id=receipt_id,
        nct_id=nct_id,
        registry_version=registry_version,
    )
    packet = compile_clinicaltrials_gov_inventory(spec, bundle)
    failures = validate_clinicaltrials_gov_inventory(spec, bundle, packet)
    if failures:
        raise ValueError(f"{nct_id} inventory replay failed: {failures}")
    return packet, bundle


def compile_preflight(
    *,
    cohort_id: str,
    registry_version: str,
    retrieved_at: datetime,
    source_paths: dict[str, str],
    source_hashes: dict[str, str],
    max_source_bytes: int,
    max_endpoint_candidate_count: int,
    max_pair_count: int,
    max_structural_array_record_count: int,
):
    if set(source_paths) != set(source_hashes):
        raise ValueError("study and source-sha256 NCT sets must match exactly")
    if len(source_paths) < 2:
        raise ValueError("at least two exact studies are required")
    if max_source_bytes <= 0:
        raise ValueError("max_source_bytes must be positive")
    inventory_bundles = tuple(
        _inventory(
            nct_id,
            Path(source_paths[nct_id]),
            source_hashes[nct_id],
            registry_version,
            retrieved_at,
            max_source_bytes,
        )
        for nct_id in sorted(source_paths)
    )
    inventories = tuple(item[0] for item in inventory_bundles)
    bundles = tuple(item[1] for item in inventory_bundles)
    candidate_spec = ClinicalTrialsGovHarmonizationCandidateSpec(
        packet_id=f"{cohort_id}-cross-trial-candidates:{registry_version}",
        inventory_bindings=tuple(
            ClinicalTrialsGovHarmonizationInventoryBinding(
                inventory_id=packet.inventory_id,
                nct_id=packet.nct_id,
                inventory_sha256=packet.fingerprint,
            )
            for packet in inventories
        ),
        max_endpoint_candidate_count=max_endpoint_candidate_count,
        max_pair_count=max_pair_count,
    )
    candidate = compile_clinicaltrials_gov_harmonization_candidates(
        candidate_spec, tuple(reversed(inventories))
    )
    failures = validate_clinicaltrials_gov_harmonization_candidates(
        candidate_spec, inventories, candidate
    )
    if failures:
        raise ValueError(f"candidate graph replay failed: {failures}")
    diagnostic_spec = ClinicalTrialsGovHarmonizationDiagnosticSpec(
        report_id=f"{cohort_id}-harmonization-difficulty:{registry_version}",
        candidate_packet_sha256=candidate.fingerprint,
    )
    diagnostic = compile_clinicaltrials_gov_harmonization_diagnostic(
        diagnostic_spec, candidate
    )
    failures = validate_clinicaltrials_gov_harmonization_diagnostic(
        diagnostic_spec, candidate, diagnostic
    )
    if failures:
        raise ValueError(f"diagnostic replay failed: {failures}")
    structure_spec = ClinicalTrialsGovHarmonizationStructureSpec(
        report_id=f"{cohort_id}-structure-decomposition:{registry_version}",
        candidate_packet_sha256=candidate.fingerprint,
        diagnostic_report_sha256=diagnostic.fingerprint,
    )
    structure = compile_clinicaltrials_gov_harmonization_structure(
        structure_spec, candidate, diagnostic
    )
    failures = validate_clinicaltrials_gov_harmonization_structure(
        structure_spec, candidate, diagnostic, structure
    )
    if failures:
        raise ValueError(f"structure replay failed: {failures}")
    sidecars = []
    for inventory, bundle in zip(inventories, bundles, strict=True):
        sidecar_spec = ClinicalTrialsGovStructuralPresenceSpec(
            sidecar_id=(
                f"{inventory.nct_id}:structural-array-presence:{registry_version}"
            ),
            inventory_sha256=inventory.fingerprint,
            source_content_hash_sha256=bundle.receipt.content_hash,
            max_structural_array_record_count=max_structural_array_record_count,
        )
        sidecar = compile_clinicaltrials_gov_structural_presence(
            sidecar_spec, bundle, inventory
        )
        failures = validate_clinicaltrials_gov_structural_presence(
            sidecar_spec, bundle, inventory, sidecar
        )
        if failures:
            raise ValueError(
                f"{inventory.nct_id} presence sidecar replay failed: {failures}"
            )
        sidecars.append(sidecar)
    bindings = tuple(
        StructuralPresenceSidecarBinding(
            nct_id=sidecar.nct_id,
            inventory_sha256=sidecar.inventory_sha256,
            sidecar_sha256=sidecar.fingerprint,
        )
        for sidecar in sidecars
    )
    presence_spec = ClinicalTrialsGovHarmonizationPresenceSpec(
        report_id=f"{cohort_id}-presence-resolution:{registry_version}",
        candidate_packet_sha256=candidate.fingerprint,
        structure_report_sha256=structure.fingerprint,
        sidecar_bindings=bindings,
    )
    presence = compile_clinicaltrials_gov_harmonization_presence(
        presence_spec, candidate, structure, sidecars
    )
    failures = validate_clinicaltrials_gov_harmonization_presence(
        presence_spec, candidate, structure, sidecars, presence
    )
    if failures:
        raise ValueError(f"presence resolution replay failed: {failures}")
    preflight_spec = ClinicalTrialsGovEndpointEstimandPreflightSpec(
        packet_id=f"{cohort_id}-endpoint-estimand-preflight:{registry_version}",
        candidate_packet_sha256=candidate.fingerprint,
        presence_report_sha256=presence.fingerprint,
        sidecar_bindings=bindings,
        max_pair_count=max_pair_count,
    )
    preflight = compile_clinicaltrials_gov_endpoint_estimand_preflight(
        preflight_spec, candidate, presence, tuple(reversed(sidecars))
    )
    failures = validate_clinicaltrials_gov_endpoint_estimand_preflight(
        preflight_spec, candidate, presence, sidecars, preflight
    )
    if failures:
        raise ValueError(f"endpoint/estimand preflight replay failed: {failures}")
    return preflight_spec, preflight, candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort-id", required=True)
    parser.add_argument(
        "--registry-version", required=True, type=_registry_version
    )
    parser.add_argument("--retrieved-at", required=True, type=_retrieved_at)
    parser.add_argument(
        "--study",
        action="append",
        required=True,
        type=_assignment,
        help="Exact source file as NCT########=/path/to/source.json; repeat per trial.",
    )
    parser.add_argument(
        "--source-sha256",
        action="append",
        required=True,
        type=_hash_assignment,
        help="Expected raw source hash as NCT########=SHA256; repeat per trial.",
    )
    parser.add_argument("--max-endpoint-candidate-count", type=int, default=1000)
    parser.add_argument("--max-pair-count", type=int, default=10000)
    parser.add_argument(
        "--max-source-bytes", type=int, default=DEFAULT_MAX_SOURCE_BYTES
    )
    parser.add_argument(
        "--max-structural-array-record-count", type=int, default=10000
    )
    parser.add_argument("--spec-output", required=True, type=Path)
    parser.add_argument("--packet-output", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    source_paths = _unique_assignments(args.study, "study")
    source_hashes = _unique_assignments(args.source_sha256, "source-sha256")
    spec, packet, _candidate = compile_preflight(
        cohort_id=args.cohort_id,
        registry_version=args.registry_version,
        retrieved_at=args.retrieved_at,
        source_paths=source_paths,
        source_hashes=source_hashes,
        max_source_bytes=args.max_source_bytes,
        max_endpoint_candidate_count=args.max_endpoint_candidate_count,
        max_pair_count=args.max_pair_count,
        max_structural_array_record_count=(
            args.max_structural_array_record_count
        ),
    )
    write_json_artifact(
        args.spec_output,
        clinicaltrials_gov_endpoint_estimand_preflight_spec_to_dict(spec),
        force=args.force,
    )
    write_json_artifact(
        args.packet_output,
        clinicaltrials_gov_endpoint_estimand_preflight_packet_envelope(packet),
        force=args.force,
    )
    print(
        json.dumps(
            clinicaltrials_gov_endpoint_estimand_preflight_summary(packet),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
