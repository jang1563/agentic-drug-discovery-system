#!/usr/bin/env python3
"""Fail-closed audit for files that would be committed to GitHub."""

from __future__ import annotations

import argparse
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
    re.compile(r"(OPENAI|ANTHROPIC|AWS|GITHUB|HF)_[A-Z0-9_]*(KEY|TOKEN|SECRET)\s*=", re.I),
    re.compile(r"BEGIN (RSA|OPENSSH|EC|DSA) PRIVATE KEY"),
)

FORBIDDEN_CONTENT_PATTERNS = (
    re.compile("/" + "Users" + r"/[^\\s`'\"]+"),
    re.compile("/" + "home" + r"/fs\d+/[^\\s`'\"]+"),
    re.compile("/" + "expanse" + "/" + "lustre" + r"/[^\\s`'\"]+"),
    re.compile(r"\b(?:" + "|".join(("j" + "kim", "ja" + "k", "cr" + "l")) + r")\d{2,}\b", re.I),
    re.compile(r"\b" + "Sch" + "midt" + r"\b", re.I),
    re.compile("Oppor" + "tunity" + "_Record"),
    re.compile("project" + "_in" + "ternal", re.I),
    re.compile("appr" + "oval" + "_tok" + "en", re.I),
)

TEXT_SUFFIXES = {
    ".cfg",
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
    return path.suffix in TEXT_SUFFIXES or path.name in {".gitignore", "Dockerfile"}


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
