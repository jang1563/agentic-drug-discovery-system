# Verifiers

Verifier types:

- `deterministic/`: exact checks and hard constraints.
- `soft/`: evidence-weighted plausibility and uncertainty scores.
- `calibration/`: score calibration, conformal thresholds, abstention policies.
- `human_review/`: escalation criteria and review packet format.

The verifier layer should be logged separately from the LLM agent. The LLM may consume verifier outputs, but should not be the only source of verification.

