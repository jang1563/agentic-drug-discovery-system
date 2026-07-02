# Project Brief

## Working Name

Agentic Drug Discovery System

## One-Line Aim

Build a research-grade blueprint and prototype environment for long-horizon drug discovery agents that are constrained by deterministic checks and guided by soft scientific verifiers.

## Hypothesis

Drug discovery can be modeled as a sequence of structured decision points rather than a single prompt-response task. If each step records the state, evidence, tools used, model outputs, verifier results, and decision rationale, then both successful and failed discovery paths can become reusable training and evaluation trajectories.

## System Ingredients

- LLM agent: plans, routes tools, updates hypotheses, explains decisions.
- Scientific foundation models: protein, chemical, cell, genome, and perturbation representations.
- Tools and databases: retrieval, docking/structure, ADMET/toxicity, omics, pathway, literature, and known-assay sources.
- Deterministic verifiers: schema, entity, unit, provenance, constraint, leakage, and reproducibility checks.
- Soft verifiers: evidence sufficiency, uncertainty, plausibility, novelty, risk, and actionability scores.
- Reward layer: step rewards, verifier rewards, information gain, cost penalties, and terminal outcome rewards.

## Scope

Initial scope should focus on an offline/safe benchmark environment, not wet-lab automation. Candidate chains:

- target identification to hit triage,
- hit-to-lead prioritization,
- lead optimization with ADMET constraints,
- protein design / binder design,
- cell perturbation response reasoning.

## Compute Split

- Local: schemas, toy environments, deterministic verifier prototypes.
- Cluster GPU: SFM embedding, structure/chemistry validation, bridge experiments, smaller calibration runs.
- Large GPU: model serving, larger rollouts, and post-training or RL-style experiments.

## Near-Term Deliverables

- v0 state/action/observation schema.
- v0 verifier contract.
- v0 reward decomposition.
- first success/failure case library.
- compute-agnostic smoke plans that can be adapted to local or cluster environments.
