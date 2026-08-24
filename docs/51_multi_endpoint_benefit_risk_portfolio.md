# Multi-Endpoint Benefit-Risk Portfolio

## Research question

Can multiple committed cross-trial endpoint syntheses be inspected together without treating a
repeated trial, endpoint, serious-safety record, or source artifact as new independent evidence?

The `clinical_benefit_risk_portfolio` layer answers that contract question. It does not combine
effects. It replays each selected `BenefitRiskSynthesisRecord` against one exact `ProgramState`,
keeps endpoint domains separate, and materializes the reuse structure that a flat list of
syntheses hides.

## Why this layer is needed

A trial commonly contributes more than one efficacy domain while the same safety population and
source artifact are reused. Counting every endpoint-domain row as a new safety observation would
inflate apparent evidence breadth. Distinct endpoint-family labels can also point to the same
endpoint record if a reviewed mapping is reused or rebound.

The portfolio therefore reports three denominators for every evidence surface:

| Surface | Reference count | Unique count | Reuse count |
| --- | --- | --- | --- |
| Endpoint | Every endpoint-domain cell | Unique `(trial_id, endpoint_id)` | References minus unique records |
| Trial | Every endpoint-domain trial cell | Unique trial ids | References minus unique trials |
| Safety | Every endpoint cell's safety link | Fingerprint-bound safety units | References minus unique units |
| Source | Every study-level source-hash link | Unique content hashes | References minus unique hashes |

Reuse is descriptive provenance structure. It is never converted into an independence weight or
an effective sample size.

## Strict and diagnostic modes

`require_distinct_endpoint_records=true` is the strict multi-endpoint mode. Two endpoint domains
cannot reuse the same `(trial_id, endpoint_id)`. This blocks relabeling one endpoint record as
apparent endpoint breadth.

`require_distinct_endpoint_records=false` is an audit mode. It permits the repeated endpoint but
sets `distinct_endpoint_records_across_domains=false` and exposes endpoint, trial, safety, and
source reuse counts. The mode is useful for finding double counting; it is not a multi-endpoint
evidence claim.

Both modes require:

- at least two distinct endpoint families;
- exact candidate, intervention, and disease continuity;
- full committed-history validation of the source state;
- successful recompilation of every selected benefit-risk synthesis;
- source-disjoint trials inside each endpoint domain;
- a one-to-one safety identity across trial, design, safety id, fingerprint, counts, time frame,
  and source hashes; and
- one trial identity per source content hash across the portfolio.

## Output structure

`ClinicalBenefitRiskPortfolioReport` contains:

- endpoint-domain records with exact estimates, intervals, units, time frames, benefit direction,
  endpoint fingerprints, safety measure, harmonization policy, safety-direction consistency, and
  safety-unit links;
- deduplicated safety units with raw numerators, denominators, observed risks, risk differences,
  time frames, fingerprints, and every referencing endpoint family;
- source units with one content hash, one trial identity, and every referencing synthesis, endpoint
  family, and safety unit;
- exact reference, unique, and reuse counts; and
- fixed false fields for pooling, scalar benefit-risk scoring, cross-endpoint comparability,
  safety independence, and clinical acceptability.

Specification and report envelopes carry canonical SHA-256 integrity digests. Strict parsers reject
unknown fields, duplicate JSON keys, non-finite values, noncanonical ordering, count drift, identity
rebinding, effect-scale or direction contradictions, and integrity mismatch. State-bound validation
still requires full recompilation; an envelope digest alone is not source authentication.

## Executable contract

```python
from agentic_drug_discovery import (
    ClinicalBenefitRiskPortfolioSpec,
    clinical_benefit_risk_portfolio_report_envelope,
    compile_clinical_benefit_risk_portfolio,
    validate_clinical_benefit_risk_portfolio,
)

spec = ClinicalBenefitRiskPortfolioSpec(
    portfolio_id="candidate:disease:multi-endpoint:v1",
    candidate_id="candidate",
    intervention_id="intervention",
    disease_id="disease",
    synthesis_ids=("endpoint-a-synthesis", "endpoint-b-synthesis"),
)
report = compile_clinical_benefit_risk_portfolio(state, spec)
assert validate_clinical_benefit_risk_portfolio(state, spec, report) == ()
payload = clinical_benefit_risk_portfolio_report_envelope(report)
```

Machine contracts:

- `rl_env/specs/clinical_benefit_risk_portfolio_spec.schema.json`
- `rl_env/specs/clinical_benefit_risk_portfolio_report.schema.json`

## Current result and boundary

The executable synthetic study commits two endpoint mappings and two benefit-risk syntheses through
the normal stage runner. A strict four-trial arrangement retains four endpoint, safety, and source
units with zero reuse. A diagnostic two-trial arrangement deliberately reuses the same endpoint,
safety, and source records across both endpoint-family labels; the report retains four references
but only two unique units on each surface and records reuse of two.

This establishes contract behavior and failure preservation only. The second synthetic endpoint
label is not a claim about source semantics. No real multi-endpoint portfolio, ontology review,
clinical comparison, pooled efficacy result, safety conclusion, treatment recommendation, or
external validation is claimed.
