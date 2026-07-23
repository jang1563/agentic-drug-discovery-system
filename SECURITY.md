# Security Policy

## Scope

This repository is intended to publish the typed execution core, schemas, verifier contracts, adapters, and release-audit logic for an offline drug-discovery decision environment.

Do not submit or attach:

- API keys, tokens, credentials, `.env*` files, or private key material.
- Raw clinical/regulatory snapshots, hidden gold labels, locked episodes, or evaluator-only data.
- Human-subject data, unpublished collaborator data, local machine paths, scheduler logs, or generated run artifacts.
- Tool requests and raw execution ledgers without an explicit release-boundary review; typed records can still contain sensitive query arguments or adapter payloads.
- Evaluator label identifiers embedded in agent-visible state or generated trajectory records.

## Reporting

Use GitHub Security Advisories when reporting a sensitive issue after the repository is public. If the issue involves leaked credentials or private data, do not open a public issue or pull request with the sensitive material.

## Release Guardrail

Before public visibility changes or release tags, run:

```bash
python3 -m pip install -e . -e ./benchmark pytest build ruff
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
