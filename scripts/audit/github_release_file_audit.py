#!/usr/bin/env python3
"""Fail-closed audit for files that would be committed to GitHub."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


FORBIDDEN_PATH_FRAGMENTS = (
    "case_banks/clinical_regulatory_v0/source_snapshots/raw/",
    "case_banks/clinical_regulatory_v0/locked_episodes/",
    "case_banks/clinical_regulatory_v0/reward_results/",
    "verifiers/deterministic/results/",
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
    re.compile(r"hf_[A-Za-z0-9_-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(OPENAI|ANTHROPIC|AWS|GITHUB|HF)_[A-Z0-9_]*(KEY|TOKEN|SECRET)\s*=", re.I),
    re.compile(r"BEGIN (RSA|OPENSSH|EC|DSA)? ?PRIVATE KEY"),
)

FORBIDDEN_CONTENT_PATTERNS = (
    re.compile("/" + "Users" + r"/[^\\s`'\"]+"),
    re.compile("/" + "home" + r"/fs\d+/[^\\s`'\"]+"),
    re.compile("/" + "expanse" + "/" + "lustre" + r"/[^\\s`'\"]+"),
    re.compile(r"\b(Cayuga|Expanse)\b"),
    re.compile(r"\bSlurm job\s+\d{6,}\b", re.I),
    re.compile(r"\b(?:" + "|".join(("j" + "kim", "ja" + "k", "cr" + "l")) + r")\d{2,}\b", re.I),
    re.compile(r"\b" + "Sch" + "midt" + r"\b", re.I),
    re.compile("Oppor" + "tunity" + "_Record"),
    re.compile("project" + "_in" + "ternal", re.I),
    re.compile("appr" + "oval" + "_tok" + "en", re.I),
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
    "docs/public_release_readiness_plan.md",
    "release_manifest.json",
)

REQUIRED_MANIFEST_CHECKS = {
    "python3 scripts/audit/github_release_file_audit.py",
    "git diff --check",
    "python3 -m compileall adapters chains scripts/audit",
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
            errors.append(f"required public-release file missing from candidate set: {required}")

    try:
        manifest = json.loads(Path("release_manifest.json").read_text(encoding="utf-8"))
    except Exception as exc:
        return errors + [f"release_manifest.json is not valid JSON: {exc}"]

    include = set((manifest.get("public_boundary") or {}).get("include") or [])
    for required in REQUIRED_PUBLIC_FILES:
        if required not in include and required != "release_manifest.json":
            errors.append(f"release_manifest.json does not include required public file: {required}")

    checks = {c.get("command") for c in (manifest.get("required_checks") or []) if isinstance(c, dict)}
    missing_checks = REQUIRED_MANIFEST_CHECKS - checks
    for command in sorted(missing_checks):
        errors.append(f"release_manifest.json missing required check command: {command}")

    def read_required_text(rel: str) -> str:
        path = Path(rel)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")

    cff = read_required_text("CITATION.cff")
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
    if path.as_posix() != "scripts/audit/github_release_file_audit.py":
        for pattern in FORBIDDEN_CONTENT_PATTERNS:
            if pattern.search(content):
                hits.append(f"forbidden repo-boundary pattern matched: {pattern.pattern}")
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
                errors.append(f"large tracked/candidate file > {max_file_mb:.1f} MB: {rel} ({size} bytes)")
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
        print("ERROR: run this audit from the repository root after git init", file=sys.stderr)
        return 2

    errors, warnings = audit(args.max_file_mb)
    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"FAILED: {len(errors)} error(s), {len(warnings)} warning(s)", file=sys.stderr)
        return 1

    tracked_or_candidate_count = len(candidate_files())
    print(f"PASS: {tracked_or_candidate_count} tracked/candidate files audited")
    print(f"PASS: no forbidden paths, oversized files, or credential-like strings found")
    return 0


if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parents[2])
    raise SystemExit(main())
