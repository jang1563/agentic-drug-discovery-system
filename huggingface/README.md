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

This is the Hugging Face Dataset-card package for the Agentic Drug Discovery System public artifact. It is prepared as an artifact mirror for schemas, release metadata, and safety-boundary documentation. It is not a model release and does not contain raw clinical/regulatory snapshots, hidden labels, locked episodes, generated trajectories, scheduler logs, local paths, credentials, or unpublished working notes.

## Intended Use

- Review the public system architecture and release boundary.
- Inspect schema and verifier-contract documentation.
- Track provenance for the public artifact surface.
- Mirror the GitHub release once the GitHub review and Hugging Face package validation pass.

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
git diff --check
python3 -m compileall adapters chains scripts/audit
```

## Proposed Hub Placement

- Repository type: Dataset
- Proposed repo id: `jang1563/agentic-drug-discovery-system`
- Initial visibility: private
- Public visibility: only after final boundary review

## Source

Primary source repository:

`https://github.com/jang1563/agentic-drug-discovery-system`
