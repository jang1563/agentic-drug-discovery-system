# Long-Horizon Chain Design

## Candidate Chains

### Target ID to Hit

1. define disease/context state
2. retrieve target evidence
3. score target tractability
4. propose modality class
5. generate or retrieve candidate hits
6. verify entity/provenance/evidence
7. rank hit hypotheses

### Hit to Lead

1. normalize hit structures/entities
2. retrieve assay and analog evidence
3. predict potency/selectivity/ADMET
4. propose modifications
5. verify chemistry constraints
6. score multi-objective tradeoffs
7. stop, continue, or escalate

### Lead Optimization

1. maintain candidate set
2. run property predictors and structural tools
3. detect failure modes
4. propose next optimization action
5. update uncertainty and cost state
6. choose next candidate or stopping rule

### Protein / Binder Design

1. select target and binding objective
2. generate candidate binder or sequence
3. run structural predictor
4. score interface metrics
5. check novelty and risk constraints
6. rank candidates

### Cell Perturbation

1. define cell state and perturbation goal
2. retrieve perturbation evidence
3. run cell or gene model
4. compare predicted response with known signatures
5. score mechanism plausibility
6. choose follow-up perturbation or stop

## Cross-Cutting State Fields

- biological target
- chemical/protein candidate
- disease/context
- evidence records
- tool outputs
- SFM embeddings or predictions
- verifier results
- uncertainty estimates
- decision history
- cost and compute budget
- stop/escalate state

