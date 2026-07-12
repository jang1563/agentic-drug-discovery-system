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
- Root-level cluster scheduler `.out` / `.err` logs.
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

The scientific claim anchors are `docs/12_scd_vertical_slice.md`,
`docs/13_target_id_governance_node.md`, and
`docs/public_evidence_summary.json`; `scripts/audit/validate_vertical_slice_doc.py`
keeps their aggregate values and limitations synchronized.

## GitHub and Hugging Face Split

- GitHub contains the full sanitized public code surface: adapters, chains,
  verifiers, governance docs, automation, and `benchmark/`.
- The Hugging Face Dataset repository is a commit-pinned subset: documentation,
  schemas, aggregate evidence, audit code, and the `benchmark/` scorer.
- `benchmark/` scores the separately hosted
  `jang1563/clinical-trial-decision-benchmark` dataset. Its data rows and
  Croissant metadata do not belong in the Agentic Drug Discovery System mirror.
- `scripts/audit/build_hf_release_package.py` reads bytes from an explicit Git
  commit, not from the working tree. Local uncommitted work therefore cannot be
  mislabeled with the source commit and does not unnecessarily block packaging.

## Public-Readiness Gate

Before changing repository visibility, the tracked release surface must satisfy all of the following:

- `python3 scripts/audit/github_release_file_audit.py` passes on tracked and unignored candidate files.
- `python3 scripts/audit/validate_hf_release_package.py` passes before any Hugging Face upload.
- `python3 scripts/audit/build_hf_release_package.py --output /tmp/agentic-hf-release-package --force` can reproduce the Hugging Face package locally.
- `python3 scripts/audit/validate_hf_release_package.py --package /tmp/agentic-hf-release-package` confirms the exact file set, source tree, sizes, and hashes.
- `python3 -m pytest -q benchmark/tests` passes after installing the local benchmark package.
- `git diff --check` reports no whitespace errors.
- Python scaffold files compile with `python3 -m compileall adapters chains benchmark/src scripts/audit`.
- `docs/public_release_readiness_plan.md`, `release_manifest.json`, `codemeta.json`, `.zenodo.json`, and `huggingface/release_manifest.json` match the intended release scope.
- License, citation metadata, contributor guidance, pull request boundary checks, issue templates, and security reporting instructions are present.
