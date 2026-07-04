# Chain Workspaces

Each chain should define:

- initial state
- allowed tools
- state transitions
- deterministic verifier gates
- soft verifier scores
- success conditions
- failure traps
- candidate reward signals

## Implemented orchestrators

- `discovery_flow.py` — the validated 4-stage sickle cell disease decision flow:
  the action space (advance / stop / defer / request_more_evidence / flag), the
  five-tool `Toolbox`, and both curated and autonomous ReAct tool-use modes.
  See `docs/12_scd_vertical_slice.md`.
- `episode_flow.py` — per-episode flow orchestration and the policy seam an
  LLM policy slots into.

## Roadmap chain directories (placeholders)

These are empty `.gitkeep` placeholders for roadmap stages — no implemented
content lives there yet:

- `target_id_to_hit/`
- `hit_to_lead/`
- `lead_optimization/`
- `admet_tox/`
- `protein_design/`
- `cell_perturbation/`

