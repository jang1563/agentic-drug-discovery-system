# Contributing

This project is a research scaffold for safety-oriented drug-discovery decision environments. Contributions should strengthen schemas, verifier contracts, adapters, calibration logic, documentation, and release hygiene.

## Boundary

Do not contribute raw source snapshots, hidden labels, locked episodes, generated verifier results, scheduler logs, local paths, credentials, or unpublished working notes. Public examples should be synthetic, public-only, or separately audited.

## Before Opening a PR

Run:

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

## Scientific Claims

Keep claims tied to provenance, uncertainty, and scope. Adapters should be cache-first where possible, live calls should be opt-in, and model outputs should be treated as fallible evidence rather than authority.
