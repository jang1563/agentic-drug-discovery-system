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
git diff --check
python3 -m compileall adapters chains scripts/audit
```
