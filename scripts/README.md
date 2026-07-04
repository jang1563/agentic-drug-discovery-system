# Scripts

Script groups:

- `audit/`: repository-boundary and dependency checks.
- `audit/build_hf_release_package.py`: creates the local Hugging Face Dataset mirror package from `huggingface/release_manifest.json` without uploading it.

Execution and sync wrappers are kept outside Git until they are sanitized for a specific release target. Scripts should avoid embedding secrets, machine-specific paths, or local account names.
