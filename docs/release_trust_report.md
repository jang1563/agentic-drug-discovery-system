# Release Trust Report

Last reviewed: 2026-07-04

This report summarizes what the public GitHub repository and Hugging Face Dataset mirror are intended to prove, what they do not prove, and which files machines should inspect first.

## Trust Claims

| Claim | Evidence | Boundary |
| --- | --- | --- |
| The public artifact is intentionally scoped. | `docs/release_boundary.md`, `release_manifest.json`, `huggingface/release_manifest.json` | Raw source snapshots, evaluator-only labels, locked episodes, generated trajectories, logs, credentials, local paths, and model weights are excluded. |
| The release decision is machine-readable. | `release_decision_packet.json` | Visibility changes still require explicit human approval; the packet is not an approval substitute. |
| The SCD vertical slice is caveats-first. | `docs/12_scd_vertical_slice.md`, `scripts/audit/validate_vertical_slice_doc.py` | The slice is one disease, small-N, and not evidence of broad clinical prediction or autonomous drug design capability. |
| The Hugging Face mirror is reproducible from GitHub main. | `scripts/audit/build_hf_release_package.py`, `upload_manifest.json` on the Hub | The builder creates the package; authenticated upload remains an explicit operator action. |
| The public surface is checked before release changes. | `.github/workflows/release-audit.yml`, `scripts/audit/` | Passing checks reduce release-boundary risk but do not certify scientific correctness. |

## Required Human Read Order

1. `README.md`
2. `docs/release_trust_report.md`
3. `docs/12_scd_vertical_slice.md`
4. `docs/release_boundary.md`
5. `release_manifest.json`
6. `release_decision_packet.json`
7. `huggingface/README.md`
8. `huggingface/release_manifest.json`

## Machine Anchors

| Path | Role |
| --- | --- |
| `release_manifest.json` | Canonical GitHub and Hugging Face release scope. |
| `release_decision_packet.json` | Public launch status, approval gate, and hard stops. |
| `huggingface/release_manifest.json` | Hugging Face package include/exclude list. |
| `scripts/audit/github_release_file_audit.py` | Fail-closed scan for required files, forbidden paths, large files, secrets, and machine-local breadcrumbs. |
| `scripts/audit/validate_hf_release_package.py` | Dataset-card and Hugging Face manifest validation. |
| `scripts/audit/validate_public_launch_packet.py` | Launch packet and public-state metadata validation. |
| `scripts/audit/validate_vertical_slice_doc.py` | Caveat and pointer validation for the SCD vertical slice. |
| `scripts/audit/build_hf_release_package.py` | Deterministic local build of the Hugging Face mirror package. |

## Reproducible HF Package Build

Build a local Hugging Face package without uploading:

```bash
python3 scripts/audit/build_hf_release_package.py --output /tmp/agentic-hf-release-package --force
```

The generated `upload_manifest.json` records:

- artifact name,
- repo id and repo type,
- visibility target,
- source GitHub repository,
- source commit,
- generated timestamp,
- uploaded file list.

## Interpretation Warnings

- This is a protocol and benchmark-control artifact, not a model release.
- This is not a clinical decision tool.
- The SCD slice is a validated vertical slice, not a broad multi-disease atlas.
- Public benchmark numbers should be cited only with the caveats in `docs/12_scd_vertical_slice.md`.
- The repository intentionally avoids publishing raw clinical/regulatory snapshots, evaluator-only labels, locked episodes, generated trajectories, and local execution records.

