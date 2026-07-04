# Release Boundary

This repository uses a conservative boundary so that future public or collaborator-facing releases do not inherit raw data, evaluator-only material, working notes, or generated run artifacts in Git history.

## Commit by Default

- Project overview and design docs.
- Sanitized model, tool, source, verifier, and compute registries only when they do not contain raw or evaluator-only payloads.
- Builder scripts, verifier scripts, launch scripts, and schema/reward specs.
- Templates and empty directory markers needed to reconstruct the workspace layout.

## Keep Outside Git

- Full case banks and raw source snapshots.
- Evaluator-only labels and locked episode data.
- Generated reward and verifier results.
- Run logs and machine-specific execution outputs.
- Root-level `cayuga_*.out`, `cayuga_*.err`, and Slurm logs.
- API keys, credentials, `.env*`, key material, and local machine caches.

## Generated but Potentially Shareable Later

These may become release assets after a separate audit:

- Public visible-packet examples.
- Synthetic mini case banks.
- Public-only source manifests.
- Aggregated benchmark metrics without evaluator-only labels or raw source snapshots.
- Reproducible dataset cards pointing to external archives.

## Current Policy

The GitHub repo should be treated as a sanitized scaffold and protocol layer. Full episode banks, evaluator references, raw snapshots, working notes, and run outputs stay outside Git until an explicit release packaging step creates a separate audited artifact.

## Public-Readiness Gate

Before changing repository visibility, the tracked release surface must satisfy all of the following:

- `python3 scripts/audit/github_release_file_audit.py` passes on tracked and unignored candidate files.
- `python3 scripts/audit/validate_hf_release_package.py` passes before any Hugging Face upload.
- `python3 scripts/audit/build_hf_release_package.py --output /tmp/agentic-hf-release-package --force` can reproduce the Hugging Face package locally.
- `git diff --check` reports no whitespace errors.
- Python scaffold files compile with `python3 -m compileall adapters chains scripts/audit`.
- `docs/public_release_readiness_plan.md`, `release_manifest.json`, `codemeta.json`, `.zenodo.json`, and `huggingface/release_manifest.json` match the intended release scope.
- License, citation metadata, contributor guidance, pull request boundary checks, issue templates, and security reporting instructions are present.
