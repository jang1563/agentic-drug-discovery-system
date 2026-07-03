# Public Release Readiness Plan

Status: active pre-publication plan
Release posture: keep private until all blocking gates pass
Target surface: public GitHub repository with optional Hugging Face Dataset mirror

## Objective

Prepare this repository as a premium public research artifact: readable by humans, inspectable by machines, and conservative about sensitive or nonessential internal material. The public release should communicate the system architecture, safety boundary, schemas, verifier contracts, adapter interfaces, and audit path without exposing raw source snapshots, evaluator-only labels, generated trajectories, scheduler logs, local paths, credentials, or unpublished working notes. A Hugging Face mirror, if created, should be a Dataset-card artifact mirror rather than a model release.

## Public Surface

The public GitHub surface includes:

- Top-level orientation: `README.md`, `PROJECT_BRIEF.md`, `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `CITATION.cff`, and `CHANGELOG.md`.
- Design and boundary docs: `docs/00_*` through `docs/07_*`, `docs/11_*`, `docs/release_boundary.md`, and this plan.
- Machine-readable release metadata: `release_manifest.json`, `codemeta.json`, and `.zenodo.json`.
- Hugging Face local package: `huggingface/README.md` and `huggingface/release_manifest.json`.
- Scaffold code: `adapters/`, `chains/`, `rl_env/specs/`, `rl_env/rewards/`, `verifiers/soft/README.md`, and audit scripts.
- GitHub automation: `.github/workflows/release-audit.yml`, pull request template, and issue templates.
- Empty directory markers needed to preserve the scaffold layout.

## Excluded Surface

The following stay outside Git unless a separate audited release package explicitly promotes a public-only artifact:

- Full case banks, raw source snapshots, locked episodes, hidden gold, evaluator-only labels, and generated reward/verifier outputs.
- Local working notes, imported research packs, private opportunity records, and machine-specific source maps.
- Scheduler logs, root-level run outputs, generated caches, Python bytecode, and large experiment directories.
- Credentials, API tokens, `.env*`, key material, local account names, absolute local paths, and internal compute-location breadcrumbs.

## Blocking Gates

Before changing repository visibility:

1. Boundary audit passes:

   ```bash
   python3 scripts/audit/github_release_file_audit.py
   python3 scripts/audit/validate_hf_release_package.py
   ```

2. Whitespace and scaffold sanity checks pass:

   ```bash
   git diff --check
   python3 -m compileall adapters chains scripts/audit
   ```

3. Candidate file set is reviewed:

   ```bash
   git ls-files --cached --others --exclude-standard
   git status --short --ignored
   ```

4. Release metadata is complete:

   - `release_manifest.json`, `codemeta.json`, `.zenodo.json`, and `huggingface/release_manifest.json` reflect the intended public scope.
   - `CITATION.cff` has correct public citation metadata.
   - `SECURITY.md` gives safe reporting guidance without publishing direct sensitive-contact details.
   - `LICENSE` is present and the license id is consistent across metadata.

5. Human review confirms the repo does not contain sensitive content, unpublished evaluator material, or local infrastructure breadcrumbs.

## Premium Finish Checklist

- Repository description and topics clearly frame this as safety-oriented decision infrastructure, not an autonomous wet-lab or hazardous-design tool.
- Branch protection requires the release audit workflow before merging.
- First public tag is cut only after the blocking gates pass from a clean worktree.
- README links users to the release boundary, manifest, and audit command within the first screen.
- Any future Hugging Face mirror is created only after the GitHub surface is clean, with a Dataset card that repeats the same boundary.

## Current Work Plan

1. Keep the GitHub repository private while hardening the public surface.
2. Preserve the ignored local research and run artifacts without committing them.
3. Add and maintain tracked public readiness metadata in this repository.
4. Run the audit, compile, and diff checks after each public-surface change.
5. Prepare the visibility-change commit or release tag only after a final human boundary review.
