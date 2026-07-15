#!/usr/bin/env python3
"""Validate the source and an optional built Hugging Face artifact package."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CARD = ROOT / "huggingface" / "README.md"
MANIFEST = ROOT / "huggingface" / "release_manifest.json"
RELEASE_MANIFEST = ROOT / "release_manifest.json"
EXPECTED_GITATTRIBUTES = """*.7z filter=lfs diff=lfs merge=lfs -text
*.arrow filter=lfs diff=lfs merge=lfs -text
*.bin filter=lfs diff=lfs merge=lfs -text
*.parquet filter=lfs diff=lfs merge=lfs -text
*.sqlite filter=lfs diff=lfs merge=lfs -text
"""

REQUIRED_CARD_FIELDS = {
    "pretty_name": "Agentic Drug Discovery System",
    "license": "apache-2.0",
}

REQUIRED_MANIFEST_VALUES = {
    "target_surface": "huggingface_dataset",
    "repo_type": "dataset",
    "initial_visibility": "private",
}

ALLOWED_MANIFEST_STATUSES = {
    "local_package_prepared_not_uploaded",
    "private_repo_created_uploaded",
    "public_repo_update_candidate_not_uploaded",
    "public_repo_uploaded_after_approval",
}

REQUIRED_HF_INCLUDES = {
    "huggingface/README.md",
    "docs/release_boundary.md",
    "docs/release_trust_report.md",
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
    "github/README.md",
    "pyproject.toml",
    "agentic_drug_discovery/",
    "adapters/execution_registry.py",
    "adapters/pinned_evidence_adapter.py",
    "rl_env/specs/",
    "tests/__init__.py",
    "tests/test_agent_loop.py",
    "tests/test_environment.py",
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
    "tests/fixtures/clinicaltrials_gov_study.synthetic.json",
    "benchmark/",
    "release_manifest.json",
    "scripts/audit/build_hf_release_package.py",
    "scripts/audit/github_release_file_audit.py",
    "scripts/audit/smoke_test_core_wheel.py",
    "scripts/audit/validate_hf_release_package.py",
    "scripts/audit/validate_public_launch_packet.py",
    "scripts/audit/validate_vertical_slice_doc.py",
    "huggingface/release_manifest.json",
}

REQUIRED_HF_EXCLUSIONS = {
    "raw source snapshots",
    "raw source bundles, real provider review jobs, and ingestion runs",
    "real policy checkpoints and policy-run artifacts",
    "hidden/evaluator labels",
    "credentials and key material",
}

REQUIRED_PACKAGE_FILES = {
    ".gitattributes",
    "README.md",
    "github/README.md",
    "release_manifest.json",
    "release_decision_packet.json",
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
    "pyproject.toml",
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
    "adapters/execution_registry.py",
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
    "scripts/audit/smoke_test_core_wheel.py",
    "benchmark/README.md",
    "benchmark/pyproject.toml",
    "benchmark/src/ctdbench/evaluate.py",
    "benchmark/tests/test_smoke.py",
    "huggingface/release_manifest.json",
    "upload_manifest.json",
}

FORBIDDEN_CARD_PATTERNS = (
    re.compile(r"(?:/Users|/home)/[^\s`'\"]+"),
    re.compile(r"/(?:scratch|lustre|gpfs|nfs)/[^\s`'\"]+", re.I),
    re.compile(r"\b(?:Slurm|PBS|LSF) job\s+\d{6,}\b", re.I),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bhf_[A-Za-z0-9]{30,}\b"),
    re.compile(r"BEGIN (RSA|OPENSSH|EC|DSA)? ?PRIVATE KEY"),
)

STALE_PUBLIC_CARD_PHRASES = (
    "Mirror the GitHub release once",
    "Proposed Hub Placement",
    "Validated SCD vertical slice",
    "size_categories:",
)


def parse_simple_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        raise ValueError("dataset card must start with YAML front matter")
    try:
        raw = text.split("---\n", 2)[1]
    except IndexError as exc:
        raise ValueError("dataset card front matter is not closed") from exc
    fields: dict[str, str] = {}
    for line in raw.splitlines():
        if not line or line.startswith(" ") or line.startswith("-"):
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields


def load_json(path: Path, label: str, errors: list[str]) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{label} is not valid JSON: {exc}")
        return {}


def run_git_text(args: list[str]) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return proc.stdout.strip()


def run_git_bytes(args: list[str]) -> bytes:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.stdout


def resolve_commit(ref: str) -> str:
    return run_git_text(["rev-parse", "--verify", f"{ref}^{{commit}}"])


def git_blob(commit: str, path: str) -> bytes:
    return run_git_bytes(["show", f"{commit}:{path}"])


def git_manifest(commit: str) -> dict:
    return json.loads(
        git_blob(commit, "huggingface/release_manifest.json").decode("utf-8")
    )


def expected_package_mapping(commit: str, manifest: dict) -> dict[str, str]:
    """Return package destination -> source Git path for every manifest entry."""
    mapping: dict[str, str] = {}
    for raw_entry in manifest.get("include") or []:
        entry = str(raw_entry)
        if entry == "README.md":
            mapping["README.md"] = "huggingface/README.md"
        elif entry == "github/README.md":
            mapping["github/README.md"] = "README.md"
        elif entry.endswith("/"):
            output = run_git_text(["ls-tree", "-r", "--name-only", commit, "--", entry])
            files = [line for line in output.splitlines() if line.strip()]
            if not files:
                raise ValueError(f"manifest directory has no tracked files: {entry}")
            for path in files:
                mapping[path] = path
        else:
            mapping[entry] = entry
    return mapping


def normalize_hf_entry(entry: str) -> str:
    if entry == "README.md":
        return "huggingface/README.md"
    if entry == "github/README.md":
        return "README.md"
    return entry


def validate_source() -> tuple[list[str], dict]:
    errors: list[str] = []
    if not CARD.exists():
        errors.append("missing huggingface/README.md")
        card_text = ""
    else:
        card_text = CARD.read_text(encoding="utf-8", errors="ignore")
        for pattern in FORBIDDEN_CARD_PATTERNS:
            if pattern.search(card_text):
                errors.append(
                    f"huggingface/README.md forbidden pattern matched: {pattern.pattern}"
                )
        for phrase in STALE_PUBLIC_CARD_PHRASES:
            if phrase in card_text:
                errors.append(
                    f"huggingface/README.md has stale public-release wording: {phrase}"
                )
        try:
            fields = parse_simple_frontmatter(card_text)
            for key, expected in REQUIRED_CARD_FIELDS.items():
                if fields.get(key) != expected:
                    errors.append(
                        f"huggingface/README.md front matter {key!r} must be {expected!r}"
                    )
        except ValueError as exc:
            errors.append(str(exc))

    manifest = load_json(MANIFEST, "huggingface/release_manifest.json", errors)
    release_manifest = load_json(RELEASE_MANIFEST, "release_manifest.json", errors)

    if manifest.get("release_version") != release_manifest.get("release_version"):
        errors.append("Hugging Face and canonical release versions must match")
    if manifest.get("last_public_release_version") != release_manifest.get(
        "last_public_release_version"
    ):
        errors.append("Hugging Face and canonical last-public versions must match")

    for key, expected in REQUIRED_MANIFEST_VALUES.items():
        if manifest.get(key) != expected:
            errors.append(
                f"huggingface/release_manifest.json {key!r} must be {expected!r}"
            )
    if manifest.get("repo_type") == "model":
        errors.append("Hugging Face repo_type must not be model for this artifact")
    if manifest.get("status") not in ALLOWED_MANIFEST_STATUSES:
        errors.append("Hugging Face package status is not recognized")
    if manifest.get("status") == "private_repo_created_uploaded":
        if manifest.get("current_visibility") != "private":
            errors.append("uploaded Hugging Face package must remain private")
        if not str(manifest.get("repo_url", "")).startswith(
            "https://huggingface.co/datasets/"
        ):
            errors.append(
                "uploaded Hugging Face package must declare a Dataset repo URL"
            )
    if manifest.get("status") == "public_repo_update_candidate_not_uploaded":
        if manifest.get("current_visibility") != "public":
            errors.append(
                "candidate update must preserve the public baseline visibility"
            )
        if release_manifest.get("release_stage") != "public_update_candidate":
            errors.append(
                "candidate update must use canonical public_update_candidate stage"
            )
        if manifest.get("last_public_release_version") == manifest.get(
            "release_version"
        ):
            errors.append("candidate and last-public versions must be distinct")
        if not str(manifest.get("public_visibility_gate", "")).startswith(
            "new candidate upload requires explicit human boundary review"
        ):
            errors.append("candidate update must retain the explicit approval gate")
    if manifest.get("status") == "public_repo_uploaded_after_approval":
        if manifest.get("current_visibility") != "public":
            errors.append(
                "public Hugging Face package must declare current_visibility public"
            )
        if not str(manifest.get("public_visibility_gate", "")).startswith(
            "explicit human boundary review"
        ):
            errors.append(
                "public Hugging Face package must record explicit boundary review"
            )
        if not str(manifest.get("repo_url", "")).startswith(
            "https://huggingface.co/datasets/"
        ):
            errors.append("public Hugging Face package must declare a Dataset repo URL")
        if manifest.get("repo_id") != "jang1563/agentic-drug-discovery-system":
            errors.append("public Hugging Face package must declare the repo_id")
        if "proposed_repo_id" in manifest:
            errors.append("public Hugging Face package must not use proposed_repo_id")

    include = set(manifest.get("include") or [])
    exclude = set(manifest.get("exclude") or [])
    for required in sorted(REQUIRED_HF_INCLUDES - include):
        errors.append(f"huggingface/release_manifest.json missing include: {required}")
    for required in sorted(REQUIRED_HF_EXCLUSIONS - exclude):
        errors.append(f"huggingface/release_manifest.json missing exclude: {required}")
    if "huggingface/croissant.json" in include:
        errors.append(
            "Hugging Face package must not include Croissant metadata for the external dataset"
        )
    external = manifest.get("external_dataset") or {}
    if external.get("repo_id") != "jang1563/clinical-trial-decision-benchmark":
        errors.append(
            "Hugging Face manifest must identify the separately hosted scorer dataset"
        )
    if external.get("croissant_included_here") is not False:
        errors.append(
            "Hugging Face manifest must explicitly exclude external Croissant metadata"
        )

    canonical_checks = {
        item.get("command")
        for item in release_manifest.get("required_checks") or []
        if isinstance(item, dict)
        and item.get("blocking") is True
        and isinstance(item.get("command"), str)
    }
    hf_checks = set(manifest.get("required_checks") or [])
    for command in sorted(canonical_checks - hf_checks):
        errors.append(
            f"Hugging Face manifest missing canonical blocking check: {command}"
        )

    canonical_include = set(
        ((release_manifest.get("public_boundary") or {}).get("include") or [])
    )
    for entry in sorted(include):
        normalized = normalize_hf_entry(str(entry))
        covered = normalized in canonical_include or any(
            str(prefix).endswith("/") and normalized.startswith(str(prefix))
            for prefix in canonical_include
        )
        if not covered:
            errors.append(
                f"Hugging Face include is outside the canonical public boundary: {entry}"
            )
    if (ROOT / "huggingface" / "croissant.json").exists():
        errors.append(
            "huggingface/croissant.json belongs to the external dataset and must be absent"
        )

    return errors, manifest


def validate_built_package(package: Path, source_ref: str) -> list[str]:
    errors: list[str] = []
    if not package.is_dir():
        return [f"package directory does not exist: {package}"]
    upload_path = package / "upload_manifest.json"
    upload = load_json(upload_path, "built upload_manifest.json", errors)
    try:
        expected_commit = resolve_commit(source_ref)
        expected_tree = run_git_text(["rev-parse", f"{expected_commit}^{{tree}}"])
        committed_manifest = git_manifest(expected_commit)
        mapping = expected_package_mapping(expected_commit, committed_manifest)
    except Exception as exc:
        return errors + [f"could not resolve expected package from {source_ref}: {exc}"]

    actual_files = {
        path.relative_to(package).as_posix()
        for path in package.rglob("*")
        if path.is_file()
    }
    declared_files = set(upload.get("uploaded_files") or [])
    expected_files = set(mapping) | {".gitattributes", "upload_manifest.json"}
    if actual_files != declared_files:
        errors.append(
            "built package exact file set differs from upload_manifest.json: "
            f"missing={sorted(declared_files - actual_files)} extra={sorted(actual_files - declared_files)}"
        )
    if actual_files != expected_files:
        errors.append(
            "built package exact file set differs from the source-commit manifest: "
            f"missing={sorted(expected_files - actual_files)} extra={sorted(actual_files - expected_files)}"
        )
    for required in sorted(REQUIRED_PACKAGE_FILES - actual_files):
        errors.append(f"built package missing required file: {required}")
    if "huggingface/croissant.json" in actual_files:
        errors.append(
            "built package includes Croissant metadata for the external dataset"
        )

    expected_upload_values = {
        "artifact": committed_manifest.get("artifact"),
        "repo_id": committed_manifest.get("repo_id"),
        "repo_type": committed_manifest.get("repo_type"),
        "visibility": committed_manifest.get("current_visibility"),
        "source_repository": committed_manifest.get("source_repository"),
    }
    for key, expected in expected_upload_values.items():
        if upload.get(key) != expected:
            errors.append(
                f"built package {key} must be {expected!r}, got {upload.get(key)!r}"
            )

    if upload.get("source_commit") != expected_commit:
        errors.append(
            f"built package source_commit must be {expected_commit}, got {upload.get('source_commit')}"
        )
    if upload.get("source_tree") != expected_tree:
        errors.append(
            f"built package source_tree must be {expected_tree}, got {upload.get('source_tree')}"
        )
    expected_timestamp = run_git_text(["show", "-s", "--format=%cI", expected_commit])
    if upload.get("source_commit_timestamp") != expected_timestamp:
        errors.append("built package source_commit_timestamp is not commit-derived")
    if "generated_at_utc" in upload:
        errors.append(
            "built package must not contain a wall-clock generated_at_utc field"
        )
    attributes_path = package / ".gitattributes"
    if (
        attributes_path.is_file()
        and attributes_path.read_text(encoding="utf-8") != EXPECTED_GITATTRIBUTES
    ):
        errors.append(
            "built package .gitattributes does not match the deterministic template"
        )

    records = upload.get("files") or {}
    expected_record_paths = actual_files - {"upload_manifest.json"}
    if set(records) != expected_record_paths:
        errors.append(
            "upload_manifest.json hash records do not cover the exact non-self payload set"
        )
    for rel in sorted(expected_record_paths & set(records)):
        payload = (package / rel).read_bytes()
        record = records.get(rel) or {}
        if record.get("size") != len(payload):
            errors.append(f"built package size mismatch: {rel}")
        if record.get("sha256") != hashlib.sha256(payload).hexdigest():
            errors.append(f"built package SHA-256 mismatch: {rel}")

    for destination, source in sorted(mapping.items()):
        target = package / destination
        if target.is_file() and target.read_bytes() != git_blob(
            expected_commit, source
        ):
            errors.append(
                f"built package bytes do not match source commit: {destination} <- {source}"
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--package",
        help="Optional built package directory whose exact files, hashes, and source commit are checked.",
    )
    parser.add_argument(
        "--source-commit",
        default="HEAD",
        help="Expected Git commit for --package validation (default: HEAD).",
    )
    args = parser.parse_args()

    errors, _ = validate_source()
    if args.package:
        errors.extend(
            validate_built_package(
                Path(args.package).expanduser().resolve(), args.source_commit
            )
        )

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"FAILED: {len(errors)} Hugging Face package error(s)", file=sys.stderr)
        return 1

    if args.package:
        print("PASS: Hugging Face source and built package validated")
    else:
        print("PASS: Hugging Face Dataset-card source package validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
