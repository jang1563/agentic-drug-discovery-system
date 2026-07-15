#!/usr/bin/env python3
"""Build a deterministic Hugging Face mirror from Git commit objects."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HF_MANIFEST_PATH = "huggingface/release_manifest.json"
DEFAULT_GITATTRIBUTES = """*.7z filter=lfs diff=lfs merge=lfs -text
*.arrow filter=lfs diff=lfs merge=lfs -text
*.bin filter=lfs diff=lfs merge=lfs -text
*.parquet filter=lfs diff=lfs merge=lfs -text
*.sqlite filter=lfs diff=lfs merge=lfs -text
"""


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
    try:
        return run_git_text(["rev-parse", "--verify", f"{ref}^{{commit}}"])
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"ERROR: source commit is not available: {ref}") from exc


def read_git_blob(commit: str, path: str) -> bytes:
    try:
        return run_git_bytes(["show", f"{commit}:{path}"])
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"ERROR: missing package source file at {commit[:12]}: {path}"
        ) from exc


def load_manifest(commit: str) -> dict:
    try:
        return json.loads(read_git_blob(commit, HF_MANIFEST_PATH).decode("utf-8"))
    except Exception as exc:
        raise SystemExit(
            f"ERROR: could not read {HF_MANIFEST_PATH} from {commit[:12]}: {exc}"
        ) from exc


def tracked_files_under(commit: str, prefix: str) -> list[str]:
    output = run_git_text(["ls-tree", "-r", "--name-only", commit, "--", prefix])
    return [line for line in output.splitlines() if line.strip()]


def write_blob(commit: str, source: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(read_git_blob(commit, source))


def copy_manifest_entry(commit: str, entry: str, output: Path) -> None:
    if entry == "README.md":
        write_blob(commit, "huggingface/README.md", output / "README.md")
        return
    if entry == "github/README.md":
        write_blob(commit, "README.md", output / "github" / "README.md")
        return
    if entry.endswith("/"):
        files = tracked_files_under(commit, entry)
        if not files:
            raise SystemExit(
                f"ERROR: manifest directory has no tracked files at {commit[:12]}: {entry}"
            )
        for source in files:
            write_blob(commit, source, output / source)
        return
    write_blob(commit, entry, output / entry)


def package_files(output: Path) -> list[str]:
    return sorted(
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file()
    )


def file_record(path: Path) -> dict[str, int | str]:
    payload = path.read_bytes()
    return {"sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload)}


def build_package(output: Path, force: bool, source_ref: str) -> dict:
    source_commit = resolve_commit(source_ref)
    manifest = load_manifest(source_commit)
    repo_id = manifest.get("repo_id")
    repo_type = manifest.get("repo_type")
    visibility = manifest.get("current_visibility")
    if repo_id != "jang1563/agentic-drug-discovery-system":
        raise SystemExit(
            "ERROR: huggingface/release_manifest.json repo_id is incorrect"
        )
    if repo_type != "dataset":
        raise SystemExit("ERROR: Hugging Face package must target a Dataset repo")
    if visibility != "public":
        raise SystemExit(
            "ERROR: Hugging Face package must declare current_visibility public"
        )

    if output.exists():
        if not force:
            raise SystemExit(
                f"ERROR: output path already exists; pass --force to replace it: {output}"
            )
        shutil.rmtree(output)
    output.mkdir(parents=True)

    (output / ".gitattributes").write_text(DEFAULT_GITATTRIBUTES, encoding="utf-8")
    entries = list(
        dict.fromkeys(str(entry) for entry in (manifest.get("include") or []))
    )
    for entry in entries:
        copy_manifest_entry(source_commit, entry, output)

    payload_files = package_files(output)
    file_records = {rel: file_record(output / rel) for rel in payload_files}
    upload_manifest = {
        "artifact": manifest.get("artifact"),
        "repo_id": repo_id,
        "repo_type": repo_type,
        "visibility": visibility,
        "source_repository": manifest.get("source_repository"),
        "source_commit": source_commit,
        "source_tree": run_git_text(["rev-parse", f"{source_commit}^{{tree}}"]),
        "source_commit_timestamp": run_git_text(
            ["show", "-s", "--format=%cI", source_commit]
        ),
        "uploaded_files": sorted([*payload_files, "upload_manifest.json"]),
        "files": file_records,
    }
    upload_path = output / "upload_manifest.json"
    upload_path.write_text(
        json.dumps(upload_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return upload_manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", required=True, help="Directory to create or replace."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace the output directory if it exists.",
    )
    parser.add_argument(
        "--source-commit",
        default="HEAD",
        help="Git commit to package. Files are read from its Git objects, not the working tree.",
    )
    args = parser.parse_args()

    output = Path(args.output).expanduser().resolve()
    if output == ROOT or ROOT in output.parents:
        print("ERROR: output directory must be outside the repository", file=sys.stderr)
        return 2

    manifest = build_package(output, args.force, args.source_commit)
    print(f"PASS: built Hugging Face package at {output}")
    print(f"PASS: source_commit={manifest['source_commit']}")
    print(f"PASS: source_tree={manifest['source_tree']}")
    print(f"PASS: file_count={len(manifest['uploaded_files'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
