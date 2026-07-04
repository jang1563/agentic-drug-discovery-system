# Adapters

Adapters translate external tools, databases, and models into the environment's observation schema.

## Implemented adapters

Callable adapters used by the sickle cell disease vertical slice
(`docs/12_scd_vertical_slice.md`):

- `opentargets_adapter.py` — Open Targets target–disease association.
- `chembl_adapter.py` — ChEMBL molecule / mechanism / target-activity lookup.
- `ctgov_adapter.py` — ClinicalTrials.gov trials (status, results, whyStopped, primary-endpoint significance).
- `ema_epar_adapter.py` — EMA EPAR EU regulatory status (Authorised / Suspended / Revoked / not-filed).
- `ema_ledger.py` — curated EMA reversal ledger.
- `boltz_adapter.py` — Boltz-2 structural SFM tool (binding affinity / structure), GPU-gated with an honest fallback.
- `molprops_adapter.py` — local (CPU) RDKit druglikeness signal: QED, MW, logP, H-bond donors/acceptors, Lipinski violations. No GPU required.

**Data boundary:** adapter *code* ships, but the cached data snapshots and case
banks it reads do not (see `docs/release_boundary.md`). On a clean public clone
the adapters import and compile but are illustrative-only without a user's own
cached snapshots or live API access.

## Adapter groups (layout)

- `databases/`: retrieval, entity lookup, assay and literature records.
- `sfm_models/`: protein, chemical, cell, genome, and perturbation models.
- `llm_models/`: prompt, tool-calling, vLLM, and policy interfaces.
- `external_tools/`: chemistry, structure, ADMET, and analysis tools.

Every adapter should eventually expose:

- input schema
- output schema
- provenance fields
- error format
- deterministic verifier hooks
- cost/runtime hints

