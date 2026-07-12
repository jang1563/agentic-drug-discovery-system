---
pretty_name: Agentic Drug Discovery System
license: apache-2.0
language:
  - en
tags:
  - agentic-drug-discovery
  - scientific-verification
  - bioinformatics
  - ai-safety
  - benchmark
  - decision-support
---

# Agentic Drug Discovery System

This is the Hugging Face Dataset-card package for the Agentic Drug Discovery System public artifact. It is a commit-pinned artifact mirror for documentation, schemas, aggregate evidence, release metadata, safety boundaries, and the `ctdbench` scorer. It is not a row dataset or model release and does not contain raw clinical/regulatory snapshots, hidden labels, locked episodes, generated trajectories, scheduler logs, local paths, credentials, or unpublished working notes.

## At A Glance

| Field | Value |
| --- | --- |
| Repository type | Dataset |
| Current visibility | Public |
| Contents | Documentation, schemas, aggregate evidence, manifests, audit code, and the `ctdbench` scorer. |
| Not included | Raw source data, hidden labels, generated trajectories, logs, credentials, local paths, or model weights. |
| Source commit | See `upload_manifest.json`. |

## Intended Use

- Review the public system architecture and release boundary.
- Read the caveats-first SCD vertical slice before citing benchmark numbers.
- Read the small-N target-identification results card and aggregate claim ledger.
- Inspect schema and verifier-contract documentation.
- Use `benchmark/` to score the separately hosted clinical-trial decision dataset.
- Track provenance for the public artifact surface.
- Inspect the mirrored GitHub release surface and source-commit provenance.

## Artifact Map

| Path | Purpose |
| --- | --- |
| `README.md` | This Hugging Face Dataset card. |
| `github/README.md` | GitHub README preserved inside the Hub mirror. |
| `release_manifest.json` | Cross-surface release manifest. |
| `release_decision_packet.json` | Machine-readable launch decision packet. |
| `huggingface/release_manifest.json` | Hugging Face-specific include/exclude manifest. |
| `upload_manifest.json` | Exact uploaded file list and source commit. |
| `docs/release_boundary.md` | Public-release boundary and exclusion rules. |
| `docs/release_trust_report.md` | Trust claims, machine anchors, and interpretation warnings. |
| `docs/12_scd_vertical_slice.md` | Audited SCD vertical slice, with small-N caveats. |
| `docs/13_target_id_governance_node.md` | Upstream target-identification results card. |
| `docs/public_evidence_summary.json` | Machine-readable aggregate claims and limitations. |
| `benchmark/` | Installable `ctdbench` scorer and tests. |
| `docs/public_launch_checklist.md` | Human launch checklist before any visibility change. |
| `scripts/audit/*.py` | Local release audits and reproducible Hub package builder. |

## Not Included

- Raw source snapshots or full case banks.
- Hidden/evaluator labels or locked episode records.
- Generated reward/verifier outputs or run logs.
- Credentials, local machine paths, or private infrastructure details.
- Model weights or an executable autonomous discovery system.
- Croissant metadata for `jang1563/clinical-trial-decision-benchmark`; that
  metadata belongs to the separate external dataset, not this artifact mirror.

## Linked External Dataset

The scorer in `benchmark/` targets
`https://huggingface.co/datasets/jang1563/clinical-trial-decision-benchmark`.
That dataset has its own card, rows, and Croissant metadata. This repository's
Hub package intentionally does not duplicate those data or metadata.

## Validation Before Upload

Run these checks from the GitHub repository root before creating or updating the Hugging Face repository:

```bash
python3 scripts/audit/github_release_file_audit.py
python3 scripts/audit/validate_hf_release_package.py
python3 scripts/audit/validate_public_launch_packet.py
python3 scripts/audit/validate_vertical_slice_doc.py
python3 -m pytest -q benchmark/tests
python3 scripts/audit/build_hf_release_package.py --output /tmp/agentic-hf-release-package --force
python3 scripts/audit/validate_hf_release_package.py --package /tmp/agentic-hf-release-package
git diff --check
python3 -m compileall adapters chains benchmark/src scripts/audit
```

## Hub Placement

- Repository type: Dataset
- Repo id: `jang1563/agentic-drug-discovery-system`
- Current visibility: public
- Public visibility: approved after final boundary review

## Source

Primary source repository:

`https://github.com/jang1563/agentic-drug-discovery-system`
