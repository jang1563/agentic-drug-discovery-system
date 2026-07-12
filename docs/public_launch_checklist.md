# Public Launch Checklist

This checklist is the human-readable companion to `release_decision_packet.json`.
It records the final review state for the GitHub and Hugging Face public release.
Scientific anchors: `docs/12_scd_vertical_slice.md`,
`docs/13_target_id_governance_node.md`, and
`docs/public_evidence_summary.json`. The external scorer is under `benchmark/`,
and `scripts/audit/validate_vertical_slice_doc.py` checks claim drift.

## Current Launch State

| Surface | Current state | Public action allowed now? |
| --- | --- | --- |
| GitHub | Public repository after explicit owner approval | Completed |
| Hugging Face | Public Dataset mirror after explicit owner approval | Completed |

Public visibility was authorized only after explicit human approval from the
owner and passing release-boundary checks.

## Human Review Gates

- [x] GitHub remained private until the final boundary review was approved.
- [x] Hugging Face remained private until the final boundary review was approved.
- [x] Draft PR review confirmed that the README describes the actual built scope,
  not only the roadmap.
- [x] `docs/release_boundary.md` still excludes raw source snapshots, hidden
  labels, locked episodes, generated trajectories, run logs, credentials,
  machine-local paths, and model weights.
- [x] `release_manifest.json` and `huggingface/release_manifest.json` match the
  intended release surface.
- [x] `release_decision_packet.json` says `public_released_after_human_approval`.
- [x] GitHub Actions `release-audit` is green on the public-readiness branch.
- [x] The Hugging Face mirror has been refreshed from the reviewed source commit.
- [x] The Hub package was built from Git commit objects and its exact file set,
  source tree, byte sizes, and SHA-256 values were validated before upload.
- [x] `benchmark/` tests pass, and its linked external dataset's Croissant
  metadata is absent from this artifact mirror.
- [x] The SCD and target-node aggregate claims match
  `docs/public_evidence_summary.json`; raw runs and per-record gold remain excluded.
- [x] Anonymous Hub API/page reads expose the card, source commit, and upload
  manifest after the visibility change.

## Required Local Commands

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

## Launch Decision Rule

The public release is valid only when every human review gate is checked, every
required command is green, the GitHub Actions release audit is green, and a
reviewer explicitly approves the visibility change.

If any release-boundary check regresses, return the affected surface to private
until the issue is fixed.
