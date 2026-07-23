# Contributing

This project is an evidence-governed execution system for safety-oriented drug-discovery agents. Contributions should strengthen typed state transitions, schemas, verifier contracts, adapters, calibration logic, documentation, and release hygiene.

## Boundary

Do not contribute raw source snapshots, hidden labels, locked episodes, generated verifier results, scheduler logs, local paths, credentials, or unpublished working notes. Public examples should be synthetic, public-only, or separately audited.

## Before Opening a PR

Run:

```bash
python3 -m pip install -e ".[test]" -e ./benchmark build ruff
python3 scripts/audit/github_release_file_audit.py
python3 scripts/audit/validate_hf_release_package.py
python3 scripts/audit/validate_public_launch_packet.py
python3 scripts/audit/validate_vertical_slice_doc.py
python3 -m unittest discover -s tests -v
python3 -m ruff check agentic_drug_discovery tests adapters/boltz_adapter.py adapters/chembl_adapter.py adapters/opentargets_adapter.py adapters/execution_registry.py adapters/pinned_evidence_adapter.py scripts/audit
python3 -m pytest -q benchmark/tests
python3 -m build --wheel . --outdir /tmp/agentic-core-dist
python3 scripts/audit/smoke_test_core_wheel.py --wheel-dir /tmp/agentic-core-dist
python3 scripts/audit/build_hf_release_package.py --output /tmp/agentic-hf-release-package --force
python3 scripts/audit/validate_hf_release_package.py --package /tmp/agentic-hf-release-package
git diff --check
python3 -m compileall agentic_drug_discovery adapters chains benchmark/src scripts/audit tests
```

## Scientific Claims

Keep claims tied to provenance, uncertainty, and scope. Adapters should be cache-first where possible, live calls should be opt-in, and model outputs should be treated as fallible evidence rather than authority.
