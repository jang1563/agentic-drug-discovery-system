## Summary

-

## Release Boundary Checklist

- [ ] I did not add raw source snapshots, hidden/evaluator labels, locked episodes, generated run outputs, scheduler logs, local paths, credentials, or unpublished working notes.
- [ ] I ran `python3 scripts/audit/github_release_file_audit.py`.
- [ ] I ran `git diff --check`.
- [ ] I ran `python3 -m compileall adapters chains scripts/audit` when Python files changed.
- [ ] I updated `release_manifest.json`, `codemeta.json`, `.zenodo.json`, or documentation if the public surface changed.

## Notes

-
