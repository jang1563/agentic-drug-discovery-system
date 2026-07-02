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

## Cluster GPU

- use for SFM embedding, Boltz/RDKit/ProteinMPNN validation, Qwen/BGE bridge, smaller training/eval.

## Large GPU

- use for vLLM, Qwen2.5 14B/32B trajectories, larger rollouts, and post-training/RL-style experiments.

## Current Principle

The first prototype should prefer cached outputs and deterministic replay over live expensive tools. Once the environment schema is stable, live tool adapters can be added stage by stage.
