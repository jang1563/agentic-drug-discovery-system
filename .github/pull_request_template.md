## Summary

-

## Release Boundary Checklist

- [ ] I did not add raw source snapshots, hidden/evaluator labels, locked episodes, generated run outputs, scheduler logs, local paths, credentials, or unpublished working notes.
- [ ] I ran `python3 scripts/audit/github_release_file_audit.py`.
- [ ] I ran the HF, launch-packet, and scientific-claim source validators.
- [ ] I ran `python3 -m pytest -q benchmark/tests` when benchmark code changed.
- [ ] I built and validated the exact Hugging Face package when its surface changed.
- [ ] I ran `git diff --check`.
- [ ] I ran `python3 -m compileall adapters chains benchmark/src scripts/audit` when Python files changed.
- [ ] I updated `release_manifest.json`, `codemeta.json`, `.zenodo.json`, or documentation if the public surface changed.

## Notes

-
