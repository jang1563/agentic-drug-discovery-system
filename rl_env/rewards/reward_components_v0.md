# Reward Components v0

## Step Rewards

- deterministic verifier pass
- schema correctness
- valid entity resolution
- valid tool call
- evidence provenance completeness
- uncertainty reduction
- candidate quality improvement

## Penalties

- invalid action
- missing provenance
- entity mismatch
- unsupported causal claim
- hallucinated tool output
- budget overuse
- overconfident low-evidence decision
- unsafe or premature recommendation

## Terminal Rewards

- correct success
- correct failure detection
- correct stopping under uncertainty
- recovery from failed intermediate step
- avoidance of known trap

## Reward Design Note

Keep hard constraints separate from soft scores. A hard verifier failure should block, repair, or strongly penalize the transition; a soft verifier score should shape search and stopping behavior.

