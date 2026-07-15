#!/usr/bin/env python3
"""Fail-closed audit for files that would be committed to GitHub."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path


FORBIDDEN_PATH_FRAGMENTS = (
    "case_banks/clinical_regulatory_v0/source_snapshots/raw/",
    "case_banks/clinical_regulatory_v0/locked_episodes/",
    "case_banks/clinical_regulatory_v0/reward_results/",
    "verifiers/deterministic/results/",
    "source_bundles/",
    "ingestion_runs/",
    "provider_review_jobs/",
    "__pycache__/",
)

FORBIDDEN_ROOT_PATTERNS = (
    re.compile(r"^[a-z]+_.*\.(out|err)$"),
    re.compile(r"^slurm-.*\.(out|err)$"),
)

SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bhf_[A-Za-z0-9]{30,}\b"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(
        r"(OPENAI|ANTHROPIC|AWS|GITHUB|HF)_[A-Z0-9_]*(KEY|TOKEN|SECRET)\s*=", re.I
    ),
    re.compile(r"BEGIN (RSA|OPENSSH|EC|DSA)? ?PRIVATE KEY"),
)

FORBIDDEN_CONTENT_PATTERNS = (
    re.compile(r"(?:/Users|/home)/[^\s`'\"]+"),
    re.compile(r"/(?:scratch|lustre|gpfs|nfs)/[^\s`'\"]+", re.I),
    re.compile(r"\b(?:Slurm|PBS|LSF) job\s+\d{6,}\b", re.I),
)

TEXT_SUFFIXES = {
    ".cfg",
    ".cff",
    ".csv",
    ".env",
    ".gitignore",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
    ".sbatch",
}

TEXT_NAMES = {".gitignore", "Dockerfile", "LICENSE"}

REQUIRED_PUBLIC_FILES = (
    ".github/workflows/release-audit.yml",
    ".github/pull_request_template.md",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/ISSUE_TEMPLATE/release_boundary_review.yml",
    "pyproject.toml",
    "README.md",
    "PROJECT_BRIEF.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CITATION.cff",
    "CHANGELOG.md",
    "codemeta.json",
    ".zenodo.json",
    "docs/release_boundary.md",
    "docs/release_trust_report.md",
    "docs/public_release_readiness_plan.md",
    "docs/public_launch_checklist.md",
    "docs/12_scd_vertical_slice.md",
    "docs/13_target_id_governance_node.md",
    "docs/14_target_identity_continuity.md",
    "docs/15_discovery_context_identity.md",
    "docs/16_clinical_intervention_identity.md",
    "docs/17_pinned_source_ingestion.md",
    "docs/18_cdc_mmwr_ingestion.md",
    "docs/19_ncbi_pubmed_ingestion.md",
    "docs/20_preclinical_provider_ingestion.md",
    "docs/preclinical_provider_validation_snapshot.json",
    "docs/21_clinical_provider_ingestion.md",
    "docs/clinical_provider_validation_snapshot.json",
    "docs/22_clinical_benefit_risk_synthesis.md",
    "docs/23_clinical_portfolio_endpoint_mapping.md",
    "docs/24_policy_replanning_and_resume.md",
    "docs/public_evidence_summary.json",
    "huggingface/README.md",
    "huggingface/release_manifest.json",
    "release_manifest.json",
    "release_decision_packet.json",
    "agentic_drug_discovery/__init__.py",
    "agentic_drug_discovery/bounded_demo.py",
    "agentic_drug_discovery/cdc_mmwr.py",
    "agentic_drug_discovery/chembl_activity.py",
    "agentic_drug_discovery/clinicaltrials_gov.py",
    "agentic_drug_discovery/clinical_portfolio.py",
    "agentic_drug_discovery/clinical_endpoint_mapping.py",
    "agentic_drug_discovery/clinical_synthesis.py",
    "agentic_drug_discovery/ncbi_pubmed.py",
    "agentic_drug_discovery/demo.py",
    "agentic_drug_discovery/environment.py",
    "agentic_drug_discovery/execution.py",
    "agentic_drug_discovery/ingestion.py",
    "agentic_drug_discovery/ingestion_cli.py",
    "agentic_drug_discovery/matched_evaluation.py",
    "agentic_drug_discovery/models.py",
    "agentic_drug_discovery/orchestration.py",
    "agentic_drug_discovery/planning.py",
    "agentic_drug_discovery/pinned_evidence.py",
    "agentic_drug_discovery/program.py",
    "agentic_drug_discovery/policy.py",
    "agentic_drug_discovery/promotion.py",
    "agentic_drug_discovery/replay_cli.py",
    "agentic_drug_discovery/serialization.py",
    "agentic_drug_discovery/verifiers.py",
    "adapters/boltz_adapter.py",
    "adapters/chembl_adapter.py",
    "adapters/execution_registry.py",
    "adapters/opentargets_adapter.py",
    "adapters/pinned_evidence_adapter.py",
    "adapters/clinical_synthesis_adapter.py",
    "rl_env/specs/pinned_evidence_manifest.schema.json",
    "rl_env/specs/pinned_evidence_manifest.example.json",
    "rl_env/specs/target_identity_record.schema.json",
    "rl_env/specs/target_identity_record.example.json",
    "rl_env/specs/discovery_context_identity.schema.json",
    "rl_env/specs/discovery_context_identity.example.json",
    "rl_env/specs/clinical_intervention_identity.schema.json",
    "rl_env/specs/clinical_intervention_identity.example.json",
    "rl_env/specs/source_receipt.schema.json",
    "rl_env/specs/source_receipt.example.json",
    "rl_env/specs/pinned_evidence_ingestion_job.schema.json",
    "rl_env/specs/pinned_evidence_ingestion_job.example.json",
    "rl_env/specs/pinned_evidence_ingestion_review.schema.json",
    "rl_env/specs/cdc_mmwr_ingestion_job.schema.json",
    "rl_env/specs/cdc_mmwr_ingestion_job.example.json",
    "rl_env/specs/ncbi_pubmed_ingestion_job.schema.json",
    "rl_env/specs/ncbi_pubmed_ingestion_job.example.json",
    "rl_env/specs/chembl_activity_ingestion_job.schema.json",
    "rl_env/specs/chembl_activity_ingestion_job.example.json",
    "rl_env/specs/ncbi_pubmed_disease_model_ingestion_job.schema.json",
    "rl_env/specs/ncbi_pubmed_disease_model_ingestion_job.example.json",
    "rl_env/specs/clinicaltrials_gov_ingestion_job.schema.json",
    "rl_env/specs/clinicaltrials_gov_ingestion_job.example.json",
    "rl_env/specs/clinicaltrials_gov_portfolio_job.schema.json",
    "rl_env/specs/clinicaltrials_gov_portfolio_job.example.json",
    "rl_env/specs/clinical_endpoint_mapping.schema.json",
    "rl_env/specs/clinical_endpoint_mapping.example.json",
    "rl_env/specs/clinical_benefit_risk_synthesis.schema.json",
    "rl_env/specs/clinical_benefit_risk_synthesis.example.json",
    "rl_env/specs/policy_checkpoint.schema.json",
    "tests/test_agent_loop.py",
    "tests/test_environment.py",
    "tests/test_adapter_bindings.py",
    "tests/test_execution.py",
    "tests/test_matched_evaluation.py",
    "tests/test_program_runner.py",
    "tests/test_policy_replanning.py",
    "tests/test_pinned_evidence_adapter.py",
    "tests/test_semantic_mappings.py",
    "tests/test_target_identity_continuity.py",
    "tests/test_context_identity_continuity.py",
    "tests/test_clinical_identity_continuity.py",
    "tests/test_pinned_evidence_ingestion.py",
    "tests/test_cdc_mmwr_ingestion.py",
    "tests/test_ncbi_pubmed_ingestion.py",
    "tests/test_chembl_activity_ingestion.py",
    "tests/test_ncbi_pubmed_disease_model_ingestion.py",
    "tests/test_preclinical_provider_pair.py",
    "tests/test_clinicaltrials_gov_ingestion.py",
    "tests/test_clinical_portfolio.py",
    "tests/test_clinical_benefit_risk_synthesis.py",
    "tests/fixtures/clinicaltrials_gov_study.synthetic.json",
    "scripts/audit/build_hf_release_package.py",
    "scripts/audit/smoke_test_core_wheel.py",
    "scripts/audit/validate_hf_release_package.py",
    "scripts/audit/validate_public_launch_packet.py",
    "scripts/audit/validate_vertical_slice_doc.py",
)

REQUIRED_MANIFEST_CHECKS = {
    "python3 scripts/audit/github_release_file_audit.py",
    "python3 scripts/audit/validate_hf_release_package.py",
    "python3 scripts/audit/validate_public_launch_packet.py",
    "python3 scripts/audit/validate_vertical_slice_doc.py",
    "python3 scripts/audit/build_hf_release_package.py --output /tmp/agentic-hf-release-package --force",
    "python3 scripts/audit/validate_hf_release_package.py --package /tmp/agentic-hf-release-package",
    "python3 -m unittest discover -s tests -v",
    "python3 -m ruff check agentic_drug_discovery tests adapters/boltz_adapter.py adapters/chembl_adapter.py adapters/opentargets_adapter.py adapters/execution_registry.py adapters/pinned_evidence_adapter.py adapters/clinical_synthesis_adapter.py scripts/audit",
    "python3 -m pytest -q benchmark/tests",
    "python3 -m build --wheel . --outdir /tmp/agentic-core-dist",
    "python3 scripts/audit/smoke_test_core_wheel.py --wheel-dir /tmp/agentic-core-dist",
    "git diff --check",
    "python3 -m compileall agentic_drug_discovery adapters chains benchmark/src scripts/audit tests",
}

REQUIRED_PUBLIC_EXCLUSIONS = {
    "raw source snapshots",
    "raw source bundles, real provider review jobs, and ingestion runs",
    "real policy checkpoints and policy-run artifacts",
    "hidden/evaluator labels",
    "credentials and key material",
}


def run_git(args: list[str]) -> str:
    proc = subprocess.run(
        ["git", *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return proc.stdout


def candidate_files() -> list[Path]:
    output = run_git(["ls-files", "--cached", "--others", "--exclude-standard"])
    return [Path(line) for line in output.splitlines() if line.strip()]


def is_text_candidate(path: Path) -> bool:
    return path.suffix in TEXT_SUFFIXES or path.name in TEXT_NAMES


def audit_release_metadata(files: list[Path]) -> list[str]:
    errors: list[str] = []
    candidate_set = {path.as_posix() for path in files}
    for required in REQUIRED_PUBLIC_FILES:
        if required not in candidate_set:
            errors.append(
                f"required public-release file missing from candidate set: {required}"
            )

    try:
        manifest = json.loads(Path("release_manifest.json").read_text(encoding="utf-8"))
    except Exception as exc:
        return errors + [f"release_manifest.json is not valid JSON: {exc}"]

    include = set((manifest.get("public_boundary") or {}).get("include") or [])
    exclude = set((manifest.get("public_boundary") or {}).get("exclude") or [])
    for required in sorted(REQUIRED_PUBLIC_EXCLUSIONS - exclude):
        errors.append(f"release_manifest.json missing public exclusion: {required}")

    def covered_by_manifest(rel: str) -> bool:
        return rel in include or any(
            str(prefix).endswith("/") and rel.startswith(str(prefix))
            for prefix in include
        )

    for required in REQUIRED_PUBLIC_FILES:
        if not covered_by_manifest(required):
            errors.append(
                f"release_manifest.json does not include required public file: {required}"
            )

    for rel in sorted(candidate_set):
        if Path(rel).is_file() and not covered_by_manifest(rel):
            errors.append(
                f"tracked/unignored candidate is outside release_manifest.json include scope: {rel}"
            )

    checks = {
        c.get("command")
        for c in (manifest.get("required_checks") or [])
        if isinstance(c, dict)
    }
    missing_checks = REQUIRED_MANIFEST_CHECKS - checks
    for command in sorted(missing_checks):
        errors.append(
            f"release_manifest.json missing required check command: {command}"
        )

    def read_required_text(rel: str) -> str:
        path = Path(rel)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")

    try:
        pyproject = tomllib.loads(read_required_text("pyproject.toml"))
    except Exception as exc:
        errors.append(f"pyproject.toml is not valid TOML: {exc}")
        pyproject = {}
    package_version = (pyproject.get("project") or {}).get("version")
    release_version = manifest.get("release_version")
    if package_version != release_version:
        errors.append(
            "pyproject.toml project.version must match release_manifest release_version"
        )

    release_stage = manifest.get("release_stage")
    if release_stage not in {"public_update_candidate", "public_release"}:
        errors.append("release_manifest.json release_stage is not recognized")
    metadata_version = release_version
    if release_stage == "public_update_candidate":
        metadata_version = manifest.get("last_public_release_version")
        if not metadata_version or metadata_version == release_version:
            errors.append(
                "candidate release must identify a distinct last_public_release_version"
            )

    for rel in ("codemeta.json", ".zenodo.json"):
        try:
            metadata = json.loads(read_required_text(rel))
        except Exception as exc:
            errors.append(f"{rel} is not valid JSON: {exc}")
            continue
        if metadata.get("version") != metadata_version:
            errors.append(
                f"{rel} version must match the stable public metadata version"
            )

    cff = read_required_text("CITATION.cff")
    if f'version: "{metadata_version}"' not in cff:
        errors.append(
            "CITATION.cff version must match the stable public metadata version"
        )
    if 'license: "Apache-2.0"' not in cff and "license: Apache-2.0" not in cff:
        errors.append("CITATION.cff does not declare Apache-2.0")
    if "Apache-2.0" not in read_required_text("codemeta.json"):
        errors.append("codemeta.json does not declare Apache-2.0")
    if "Apache-2.0" not in read_required_text(".zenodo.json"):
        errors.append(".zenodo.json does not declare Apache-2.0")

    return errors


def scan_file_for_secrets(path: Path) -> list[str]:
    if not is_text_candidate(path):
        return []
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return [f"could not read text file: {exc}"]

    hits = []
    for pattern in SECRET_PATTERNS:
        if pattern.search(content):
            hits.append(f"secret-like pattern matched: {pattern.pattern}")
    if path.as_posix() not in {
        "scripts/audit/github_release_file_audit.py",
        "scripts/audit/build_hf_release_package.py",
        "scripts/audit/validate_hf_release_package.py",
        "scripts/audit/validate_vertical_slice_doc.py",
    }:
        for pattern in FORBIDDEN_CONTENT_PATTERNS:
            if pattern.search(content):
                hits.append(
                    f"forbidden repo-boundary pattern matched: {pattern.pattern}"
                )
    return hits


def audit(max_file_mb: float) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    max_bytes = int(max_file_mb * 1024 * 1024)

    files = candidate_files()
    errors.extend(audit_release_metadata(files))
    for path in files:
        rel = path.as_posix()
        for fragment in FORBIDDEN_PATH_FRAGMENTS:
            if fragment in rel:
                errors.append(f"forbidden path fragment: {rel}")

        for pattern in FORBIDDEN_ROOT_PATTERNS:
            if pattern.match(rel):
                errors.append(f"forbidden root log: {rel}")

        if path.exists() and path.is_file():
            size = path.stat().st_size
            if size > max_bytes:
                errors.append(
                    f"large tracked/candidate file > {max_file_mb:.1f} MB: {rel} ({size} bytes)"
                )
            for hit in scan_file_for_secrets(path):
                errors.append(f"{rel}: {hit}")
        else:
            warnings.append(f"candidate path missing or not a file: {rel}")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-file-mb", type=float, default=5.0)
    args = parser.parse_args()

    if not Path(".git").exists():
        print(
            "ERROR: run this audit from the repository root after git init",
            file=sys.stderr,
        )
        return 2

    errors, warnings = audit(args.max_file_mb)
    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            f"FAILED: {len(errors)} error(s), {len(warnings)} warning(s)",
            file=sys.stderr,
        )
        return 1

    tracked_or_candidate_count = len(candidate_files())
    print(f"PASS: {tracked_or_candidate_count} tracked/candidate files audited")
    print("PASS: no forbidden paths, oversized files, or credential-like strings found")
    return 0


if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parents[2])
    raise SystemExit(main())
