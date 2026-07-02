# Success / Failure Case Design

## Purpose

Success and failure cases should be designed as trajectories, not isolated examples. Each case should record the decision path, evidence state, verifier outputs, and whether the agent stopped appropriately.

## Success Case Types

- known target to known drug or probe
- known target to plausible hit class
- known hit to improved lead-like candidate
- known structural binder case
- known perturbation response with recoverable mechanism

## Failure Case Types

- entity mismatch
- target disease mismatch
- assay leakage or benchmark contamination
- unsupported causal jump
- chemistry invalidity
- structure hallucination
- ADMET/toxicity constraint failure
- weak evidence treated as strong evidence
- failure to stop under uncertainty
- over-optimization against a proxy verifier

## Case Record

Each case should include:

- initial state
- allowed tools
- evaluator-only or held-out reference facts
- expected intermediate evidence
- deterministic verifier checks
- soft verifier dimensions
- terminal success/failure condition
- known traps
- preferred stop/escalation behavior
