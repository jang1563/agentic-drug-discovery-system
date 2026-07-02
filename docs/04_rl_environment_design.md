# RL Environment Design

## Environment Skeleton

- state: current evidence graph and candidate set
- action: tool call, retrieval query, SFM prediction, candidate edit, verify, stop, escalate
- observation: structured tool/model/verifier result
- reward: progress, correctness, verifier score, calibration, cost, and stopping quality
- terminal: solved, failed, unsafe/invalid, budget exhausted, or appropriate stop

## Reward Components

- deterministic pass/fail reward
- soft verifier score
- information gain
- evidence provenance reward
- uncertainty reduction
- candidate quality improvement
- cost penalty
- invalid action penalty
- premature stop penalty
- correct stop reward

## First Environment Target

Start with an offline benchmark where actions are constrained to existing records and cached tool/model outputs. This avoids expensive live tool calls while still testing planning, routing, verification, and reward design.

## Candidate Baselines

- rule-only policy
- retrieval-only policy
- prompt-only LLM
- LLM with tools but no verifier
- LLM with deterministic verifier only
- LLM with deterministic + soft verifier
- RL/RLVR-tuned policy

