# Scripts

Script groups:

- `audit/`: repository-boundary and dependency checks.

Execution and sync wrappers are kept outside Git until they are sanitized for a specific release target. Scripts should avoid embedding secrets, machine-specific paths, or local account names.
