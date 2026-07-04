# Public Launch Checklist

This checklist is the human-readable companion to `release_decision_packet.json`.
It records the final review state for the GitHub and Hugging Face public release.

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
- [x] Browser review shows readable first-screen content on desktop and mobile.

## Required Local Commands

```bash
python3 scripts/audit/github_release_file_audit.py
python3 scripts/audit/validate_hf_release_package.py
python3 scripts/audit/validate_public_launch_packet.py
git diff --check
python3 -m compileall adapters chains scripts/audit
```

## Launch Decision Rule

The public release is valid only when every human review gate is checked, every
required command is green, the GitHub Actions release audit is green, and a
reviewer explicitly approves the visibility change.

If any release-boundary check regresses, return the affected surface to private
until the issue is fixed.
