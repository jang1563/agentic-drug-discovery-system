# Model / Tool Stack

## Model Modalities

- LLM: planning, tool routing, explanation, hypothesis update.
- Protein SFM: protein sequence/structure representation and candidate validation.
- Chemical SFM: molecule representation, property prediction, analog reasoning.
- Cell SFM: perturbation response, cell-state trajectory, mechanism plausibility.
- Genome/gene SFM: variant, regulatory, gene-program, and pathway context.
- Retrieval/embedding model: evidence search and entity linking.

## Local

- use for registry, schema, verifier, and toy environment work.
- local RDKit druglikeness (QED / MW / logP / Lipinski via `adapters/molprops_adapter.py`) runs here on CPU — no GPU required.

## Cluster GPU

- use for SFM embedding, Boltz-2 / ProteinMPNN structural validation, Qwen/BGE bridge, smaller training/eval. (Only structural prediction is GPU-gated; RDKit druglikeness runs locally — see Local.)

## Large GPU

- use for vLLM, Qwen2.5 14B/32B trajectories, larger rollouts, and post-training/RL-style experiments.

## Current Principle

The public SCD prototype includes live adapters for Open Targets, ChEMBL,
ClinicalTrials.gov, openFDA, and EMA. Historical replay still requires
cutoff-safe cached evidence; future stages should add live tools only after the
schema and time-gating contract are explicit.
