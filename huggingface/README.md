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
size_categories:
  - n<1K
---

# Agentic Drug Discovery System

This is the Hugging Face Dataset-card package for the Agentic Drug Discovery System public artifact. It is prepared as a private artifact mirror for schemas, release metadata, and safety-boundary documentation. It is not a model release and does not contain raw clinical/regulatory snapshots, hidden labels, locked episodes, generated trajectories, scheduler logs, local paths, credentials, or unpublished working notes.

## At A Glance

| Field | Value |
| --- | --- |
| Repository type | Dataset |
| Current visibility | Private |
| Contents | Documentation, schemas, manifests, and release-boundary metadata. |
| Not included | Raw source data, hidden labels, generated trajectories, logs, credentials, local paths, or model weights. |
| Source commit | See `upload_manifest.json`. |

## Intended Use

- Review the public system architecture and release boundary.
- Inspect schema and verifier-contract documentation.
- Track provenance for the public artifact surface.
- Mirror the GitHub release once the GitHub review and Hugging Face package validation pass.

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
| `docs/public_launch_checklist.md` | Human launch checklist before any visibility change. |

## Not Included

- Raw source snapshots or full case banks.
- Hidden/evaluator labels or locked episode records.
- Generated reward/verifier outputs or run logs.
- Credentials, local machine paths, or private infrastructure details.
- Model weights or an executable autonomous discovery system.

## Validation Before Upload

Run these checks from the GitHub repository root before creating or updating the Hugging Face repository:

```bash
python3 scripts/audit/github_release_file_audit.py
python3 scripts/audit/validate_hf_release_package.py
python3 scripts/audit/validate_public_launch_packet.py
git diff --check
python3 -m compileall adapters chains scripts/audit
```

## Proposed Hub Placement

- Repository type: Dataset
- Repo id: `jang1563/agentic-drug-discovery-system`
- Current visibility: private
- Public visibility: only after final boundary review

## Source

Primary source repository:

`https://github.com/jang1563/agentic-drug-discovery-system`
