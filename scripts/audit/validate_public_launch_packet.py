#!/usr/bin/env python3
"""Validate the public launch decision packet and checklist."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKET = ROOT / "release_decision_packet.json"
CHECKLIST = ROOT / "docs" / "public_launch_checklist.md"
RELEASE_MANIFEST = ROOT / "release_manifest.json"
HF_RELEASE_MANIFEST = ROOT / "huggingface" / "release_manifest.json"
FULL_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")

REQUIRED_CHECKS = {
    "python3 scripts/audit/github_release_file_audit.py",
    "python3 scripts/audit/validate_hf_release_package.py",
    "python3 scripts/audit/validate_public_launch_packet.py",
    "python3 scripts/audit/validate_vertical_slice_doc.py",
    "python3 scripts/audit/validate_policy_evaluation_snapshot.py",
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

REQUIRED_EXCLUSIONS = {
    "raw source snapshots",
    "raw source bundles, real provider review jobs, and ingestion runs",
    "real sealed evaluation boards, cached episode packets, label vaults, commitment nonces, policy submissions, and per-episode evaluations",
    "hidden or evaluator-only labels",
    "locked episode records",
    "generated reward or verifier outputs",
    "run logs",
    "credentials and key material",
    "machine-local paths",
    "model weights",
}

REQUIRED_CHECKLIST_PHRASES = (
    "explicit human approval",
    "release_decision_packet.json",
    "validate_public_launch_packet.py",
)

ALLOWED_DECISION_STATUSES = {
    "candidate_pending_human_approval",
    "public_released_after_human_approval",
}

REQUIRED_READ_ORDER = {
    "README.md",
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
    "docs/25_cutoff_safe_policy_evaluation.md",
    "docs/retrospective_policy_evaluation_snapshot.json",
    "docs/public_evidence_summary.json",
    "docs/public_launch_checklist.md",
    "docs/release_boundary.md",
    "release_manifest.json",
    "huggingface/README.md",
    "huggingface/release_manifest.json",
    "pyproject.toml",
    "agentic_drug_discovery/",
    "agentic_drug_discovery/sealed_evaluation.py",
    "rl_env/specs/target_identity_record.schema.json",
    "rl_env/specs/discovery_context_identity.schema.json",
    "rl_env/specs/clinical_intervention_identity.schema.json",
    "rl_env/specs/source_receipt.schema.json",
    "rl_env/specs/pinned_evidence_ingestion_job.schema.json",
    "rl_env/specs/cdc_mmwr_ingestion_job.schema.json",
    "rl_env/specs/ncbi_pubmed_ingestion_job.schema.json",
    "rl_env/specs/chembl_activity_ingestion_job.schema.json",
    "rl_env/specs/ncbi_pubmed_disease_model_ingestion_job.schema.json",
    "rl_env/specs/clinicaltrials_gov_ingestion_job.schema.json",
    "rl_env/specs/clinicaltrials_gov_portfolio_job.schema.json",
    "rl_env/specs/clinical_endpoint_mapping.schema.json",
    "rl_env/specs/clinical_benefit_risk_synthesis.schema.json",
    "rl_env/specs/policy_checkpoint.schema.json",
    "rl_env/specs/sealed_evaluation_board.schema.json",
    "rl_env/specs/sealed_evaluation_vault.schema.json",
    "rl_env/specs/policy_evaluation_submission.schema.json",
    "rl_env/specs/policy_evaluation_report.schema.json",
    "tests/test_sealed_evaluation.py",
    "scripts/audit/validate_policy_evaluation_snapshot.py",
    "tests/",
    "benchmark/",
}

STALE_PUBLIC_GITHUB_KEYS = {
    "active_branch",
    "active_pr",
}


def load_json(path: Path, label: str, errors: list[str]) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{label} is not valid JSON: {exc}")
        return {}


def main() -> int:
    errors: list[str] = []

    packet = load_json(PACKET, "release_decision_packet.json", errors)
    release_manifest = load_json(RELEASE_MANIFEST, "release_manifest.json", errors)
    hf_release_manifest = load_json(
        HF_RELEASE_MANIFEST, "huggingface/release_manifest.json", errors
    )
    if not CHECKLIST.exists():
        errors.append("missing docs/public_launch_checklist.md")
        checklist = ""
    else:
        checklist = CHECKLIST.read_text(encoding="utf-8", errors="ignore")

    if packet.get("artifact") != "agentic-drug-discovery-system":
        errors.append("release_decision_packet.json artifact is incorrect")
    decision_status = packet.get("decision_status")
    if decision_status not in ALLOWED_DECISION_STATUSES:
        errors.append("release_decision_packet.json has an unsupported decision_status")
    if packet.get("human_readable_checklist") != "docs/public_launch_checklist.md":
        errors.append(
            "release_decision_packet.json must point to docs/public_launch_checklist.md"
        )
    if packet.get("release_version") != release_manifest.get("release_version"):
        errors.append("release decision and release manifest versions must match")
    if packet.get("last_public_release_version") != release_manifest.get(
        "last_public_release_version"
    ):
        errors.append("release decision and manifest last-public versions must match")
    if packet.get("release_version") != hf_release_manifest.get("release_version"):
        errors.append("release decision and Hugging Face manifest versions must match")
    if packet.get("last_public_release_version") != hf_release_manifest.get(
        "last_public_release_version"
    ):
        errors.append(
            "release decision and Hugging Face manifest last-public versions must match"
        )

    surfaces = packet.get("surfaces") or {}
    github = surfaces.get("github") or {}
    hf = surfaces.get("hugging_face") or {}
    if github.get("current_visibility") != "public":
        errors.append("GitHub current_visibility must be public")
    if not str(github.get("url", "")).startswith("https://github.com/"):
        errors.append("GitHub URL must point to github.com")
    if github.get("default_branch") != "main":
        errors.append("GitHub default_branch must be main after public release")
    for key in sorted(STALE_PUBLIC_GITHUB_KEYS & set(github)):
        errors.append(f"GitHub public release metadata must not keep stale key: {key}")
    if hf.get("current_visibility") != "public":
        errors.append("Hugging Face current_visibility must be public")
    if hf.get("repo_type") != "dataset":
        errors.append("Hugging Face repo_type must be dataset")
    if not str(hf.get("url", "")).startswith("https://huggingface.co/datasets/"):
        errors.append("Hugging Face URL must point to a Dataset repo")

    launch = packet.get("launch_decision") or {}
    if launch.get("human_approval_required") is not True:
        errors.append("launch_decision.human_approval_required must be true")
    if launch.get("no_public_visibility_change_without_explicit_approval") is not True:
        errors.append(
            "launch_decision must require explicit approval before public visibility"
        )
    if launch.get("no_public_update_without_explicit_approval") is not True:
        errors.append(
            "launch_decision must require explicit approval before public updates"
        )

    if decision_status == "candidate_pending_human_approval":
        if release_manifest.get("release_stage") != "public_update_candidate":
            errors.append(
                "pending candidate must use release_stage public_update_candidate"
            )
        if github.get("last_public_release_state") != "merged_to_default_branch":
            errors.append(
                "candidate metadata must preserve the last public GitHub release state"
            )
        if not str(github.get("last_public_release_pull_request", "")).startswith(
            "https://github.com/jang1563/agentic-drug-discovery-system/pull/"
        ):
            errors.append("candidate metadata must point to the last public release PR")
        if github.get("candidate_release_state") != "not_approved_or_merged":
            errors.append("GitHub candidate must remain unapproved and unmerged")
        if hf.get("candidate_release_state") != "not_uploaded":
            errors.append("Hugging Face candidate must remain not uploaded")
        if launch.get("default") != "hold_candidate_until_approval":
            errors.append(
                "pending candidate launch default must be hold_candidate_until_approval"
            )
        if launch.get("approval_record") is not None:
            errors.append("pending candidate must not carry an approval record")
        if (release_manifest.get("hugging_face") or {}).get("status") != (
            "public_repo_update_candidate_not_uploaded"
        ):
            errors.append(
                "pending candidate must record the Hugging Face update as not uploaded"
            )
    elif decision_status == "public_released_after_human_approval":
        if release_manifest.get("release_stage") != "public_release":
            errors.append("released artifact must use release_stage public_release")
        if packet.get("last_public_release_version") != packet.get("release_version"):
            errors.append(
                "released artifact must identify the current version as last public"
            )
        if github.get("release_state") != "merged_to_default_branch":
            errors.append("released GitHub state must be merged_to_default_branch")
        if not str(github.get("release_pull_request", "")).startswith(
            "https://github.com/jang1563/agentic-drug-discovery-system/pull/"
        ):
            errors.append("released metadata must point to the release PR")
        for key in ("approved_content_commit", "approved_content_tree"):
            if not FULL_GIT_SHA.fullmatch(str(github.get(key, ""))):
                errors.append(f"released GitHub metadata has invalid {key}")
        if "candidate_release_state" in github:
            errors.append("released GitHub metadata must not retain candidate state")
        if hf.get("release_state") != "uploaded_to_public_dataset":
            errors.append(
                "released Hugging Face state must be uploaded_to_public_dataset"
            )
        if hf.get("release_version") != packet.get("release_version"):
            errors.append("released Hugging Face version must match the release")
        if not FULL_GIT_SHA.fullmatch(str(hf.get("initial_content_commit", ""))):
            errors.append(
                "released Hugging Face metadata has invalid initial_content_commit"
            )
        if not isinstance(hf.get("file_count"), int) or hf.get("file_count", 0) <= 0:
            errors.append("released Hugging Face metadata must record a file count")
        if "candidate_release_state" in hf:
            errors.append(
                "released Hugging Face metadata must not retain candidate state"
            )
        if launch.get("default") != "published_after_approval":
            errors.append("released launch default must be published_after_approval")
        if not launch.get("approval_record"):
            errors.append(
                "released metadata must include the candidate approval record"
            )
        if (release_manifest.get("hugging_face") or {}).get("status") != (
            "public_repo_uploaded_after_approval"
        ):
            errors.append(
                "released canonical manifest must record the Hugging Face upload"
            )
        if hf_release_manifest.get("status") != (
            "public_repo_uploaded_after_approval"
        ):
            errors.append(
                "released Hugging Face manifest must record the approved upload"
            )
        publication_record = packet.get("publication_record") or {}
        if publication_record != release_manifest.get("publication_record"):
            errors.append(
                "decision packet and canonical manifest publication records must match"
            )
        if publication_record != hf_release_manifest.get("publication_record"):
            errors.append(
                "decision packet and Hugging Face publication records must match"
            )
        for key in (
            "approved_candidate_commit",
            "approved_candidate_tree",
            "content_publication_commit",
            "hugging_face_initial_content_commit",
        ):
            if not FULL_GIT_SHA.fullmatch(str(publication_record.get(key, ""))):
                errors.append(f"publication_record has invalid {key}")
        if publication_record.get("approved_candidate_tree") != github.get(
            "approved_content_tree"
        ):
            errors.append(
                "publication_record tree must match released GitHub content tree"
            )
        if publication_record.get("content_publication_commit") != github.get(
            "approved_content_commit"
        ):
            errors.append(
                "publication_record commit must match released GitHub content commit"
            )
        if publication_record.get("hugging_face_initial_content_commit") != hf.get(
            "initial_content_commit"
        ):
            errors.append(
                "publication_record commit must match released Hugging Face content"
            )
        if publication_record.get("hugging_face_file_count") != hf.get("file_count"):
            errors.append(
                "publication_record file count must match released Hugging Face state"
            )
        if not str(publication_record.get("github_pull_request", "")).startswith(
            "https://github.com/jang1563/agentic-drug-discovery-system/pull/"
        ):
            errors.append("publication_record must identify the GitHub pull request")
        if not str(publication_record.get("github_actions_run", "")).startswith(
            "https://github.com/jang1563/agentic-drug-discovery-system/actions/runs/"
        ):
            errors.append("publication_record must identify the GitHub Actions run")

    commands = {
        item.get("command")
        for item in packet.get("required_checks") or []
        if isinstance(item, dict) and item.get("blocking") is True
    }
    for command in sorted(REQUIRED_CHECKS - commands):
        errors.append(f"release_decision_packet.json missing blocking check: {command}")

    exclusions = set(((packet.get("release_scope") or {}).get("exclude")) or [])
    for exclusion in sorted(REQUIRED_EXCLUSIONS - exclusions):
        errors.append(f"release_decision_packet.json missing exclusion: {exclusion}")

    read_order = set(packet.get("read_order") or [])
    for required_path in sorted(REQUIRED_READ_ORDER - read_order):
        errors.append(
            f"release_decision_packet.json missing read_order entry: {required_path}"
        )

    release_hf = release_manifest.get("hugging_face") or {}
    if release_hf.get("visibility") == "public":
        if release_hf.get("repo_id") != "jang1563/agentic-drug-discovery-system":
            errors.append(
                "release_manifest.json hugging_face.repo_id is missing or incorrect"
            )
        if "proposed_repo_id" in release_hf:
            errors.append(
                "release_manifest.json must not use proposed_repo_id after public release"
            )

    checklist_phrases = [*REQUIRED_CHECKLIST_PHRASES, str(decision_status)]
    if decision_status == "candidate_pending_human_approval":
        checklist_phrases.extend(
            (
                f"{packet.get('last_public_release_version')} public baseline",
                f"{packet.get('release_version')} candidate",
            )
        )
    elif decision_status == "public_released_after_human_approval":
        checklist_phrases.extend(
            (
                f"{packet.get('release_version')} public baseline",
                f"{packet.get('release_version')} public development release",
            )
        )
    for phrase in checklist_phrases:
        if phrase not in checklist:
            errors.append(f"docs/public_launch_checklist.md missing phrase: {phrase}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"FAILED: {len(errors)} public launch packet error(s)", file=sys.stderr)
        return 1

    print("PASS: public launch decision packet validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
