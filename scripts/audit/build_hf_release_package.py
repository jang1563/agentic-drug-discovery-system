#!/usr/bin/env python3
"""Build the local Hugging Face Dataset mirror package without uploading it."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HF_MANIFEST = ROOT / "huggingface" / "release_manifest.json"
DEFAULT_GITATTRIBUTES = """*.7z filter=lfs diff=lfs merge=lfs -text
*.arrow filter=lfs diff=lfs merge=lfs -text
*.bin filter=lfs diff=lfs merge=lfs -text
*.parquet filter=lfs diff=lfs merge=lfs -text
*.sqlite filter=lfs diff=lfs merge=lfs -text
"""


def run_git(args: list[str]) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return proc.stdout.strip()


def load_manifest() -> dict:
    try:
        return json.loads(HF_MANIFEST.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"ERROR: could not read huggingface/release_manifest.json: {exc}") from exc


def tracked_files_under(prefix: str) -> list[Path]:
    output = run_git(["ls-files", prefix])
    return [ROOT / line for line in output.splitlines() if line.strip()]


def copy_file(src: Path, dst: Path) -> None:
    if not src.exists() or not src.is_file():
        raise SystemExit(f"ERROR: missing package source file: {src.relative_to(ROOT)}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def copy_manifest_entry(entry: str, output: Path) -> None:
    if entry == "README.md":
        copy_file(ROOT / "huggingface" / "README.md", output / "README.md")
        return
    if entry == "github/README.md":
        copy_file(ROOT / "README.md", output / "github" / "README.md")
        return
    if entry.endswith("/"):
        files = tracked_files_under(entry)
        if not files:
            raise SystemExit(f"ERROR: manifest directory has no tracked files: {entry}")
        for src in files:
            copy_file(src, output / src.relative_to(ROOT))
        return
    copy_file(ROOT / entry, output / entry)


def package_files(output: Path) -> list[str]:
    return sorted(path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file())


def build_package(output: Path, force: bool) -> dict:
    manifest = load_manifest()
    repo_id = manifest.get("repo_id")
    repo_type = manifest.get("repo_type")
    visibility = manifest.get("current_visibility")
    if repo_id != "jang1563/agentic-drug-discovery-system":
        raise SystemExit("ERROR: huggingface/release_manifest.json repo_id is incorrect")
    if repo_type != "dataset":
        raise SystemExit("ERROR: Hugging Face package must target a Dataset repo")
    if visibility != "public":
        raise SystemExit("ERROR: Hugging Face package must declare current_visibility public")

    if output.exists():
        if not force:
            raise SystemExit(f"ERROR: output path already exists; pass --force to replace it: {output}")
        shutil.rmtree(output)
    output.mkdir(parents=True)

    (output / ".gitattributes").write_text(DEFAULT_GITATTRIBUTES, encoding="utf-8")
    entries = list(dict.fromkeys(manifest.get("include") or []))
    for entry in entries:
        copy_manifest_entry(str(entry), output)

    upload_manifest = {
        "artifact": manifest.get("artifact"),
        "repo_id": repo_id,
        "repo_type": repo_type,
        "visibility": visibility,
        "source_repository": manifest.get("source_repository"),
        "source_commit": run_git(["rev-parse", "HEAD"]),
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "uploaded_files": [],
    }
    upload_path = output / "upload_manifest.json"
    upload_path.write_text(json.dumps(upload_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    upload_manifest["uploaded_files"] = package_files(output)
    upload_path.write_text(json.dumps(upload_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return upload_manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, help="Directory to create or replace.")
    parser.add_argument("--force", action="store_true", help="Replace the output directory if it exists.")
    args = parser.parse_args()

    output = Path(args.output).expanduser().resolve()
    if output == ROOT or ROOT in output.parents:
        print("ERROR: output directory must be outside the repository", file=sys.stderr)
        return 2

    manifest = build_package(output, args.force)
    print(f"PASS: built Hugging Face package at {output}")
    print(f"PASS: source_commit={manifest['source_commit']}")
    print(f"PASS: file_count={len(manifest['uploaded_files'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

