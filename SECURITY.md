# Security Policy

## Scope

This repository is intended to publish the scaffold, schemas, verifier contracts, adapters, and release-audit logic for an offline drug-discovery decision environment.

Do not submit or attach:

- API keys, tokens, credentials, `.env*` files, or private key material.
- Raw clinical/regulatory snapshots, hidden gold labels, locked episodes, or evaluator-only data.
- Human-subject data, unpublished collaborator data, local machine paths, scheduler logs, or generated run artifacts.

## Reporting

Use GitHub Security Advisories when reporting a sensitive issue after the repository is public. If the issue involves leaked credentials or private data, do not open a public issue or pull request with the sensitive material.

## Release Guardrail

Before public visibility changes or release tags, run:

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
