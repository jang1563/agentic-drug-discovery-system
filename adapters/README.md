# Adapters

Adapters translate external tools, databases, and models into the environment's observation schema.

Adapter groups:

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

