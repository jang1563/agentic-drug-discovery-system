# Public Launch Checklist

This checklist is the human-readable companion to `release_decision_packet.json`.
It is written for the final review immediately before changing GitHub or
Hugging Face visibility.

## Current Launch State

| Surface | Current state | Public action allowed now? |
| --- | --- | --- |
| GitHub | Private repository with draft public-readiness PR | No |
| Hugging Face | Private Dataset mirror | No |

No visibility change is authorized by this file. Public visibility requires an
explicit human approval after the checks below pass.

## Human Review Gates

- [ ] GitHub remains private until the final boundary review is approved.
- [ ] Hugging Face remains private until the final boundary review is approved.
- [ ] Draft PR review confirms that the README describes the actual built scope,
  not only the roadmap.
- [ ] `docs/release_boundary.md` still excludes raw source snapshots, hidden
  labels, locked episodes, generated trajectories, run logs, credentials,
  machine-local paths, and model weights.
- [ ] `release_manifest.json` and `huggingface/release_manifest.json` match the
  intended release surface.
- [ ] `release_decision_packet.json` says `private_ready_for_human_publication_review`.
- [ ] GitHub Actions `release-audit` is green on the public-readiness branch.
- [ ] The private Hugging Face mirror has been refreshed from the reviewed source
  commit and remains private.
- [ ] Anonymous browser review shows private access behavior before launch, and
  authenticated review shows readable first-screen content.

## Required Local Commands

```bash
python3 scripts/audit/github_release_file_audit.py
python3 scripts/audit/validate_hf_release_package.py
python3 scripts/audit/validate_public_launch_packet.py
git diff --check
python3 -m compileall adapters chains scripts/audit
```

## Launch Decision Rule

Publish only when every human review gate is checked, every required command is
green, the GitHub Actions release audit is green, and a reviewer explicitly
approves the visibility change.

Until then, the correct state is private-ready, not public.
