# Same-Trial Multi-Endpoint Structural Stress

## Research question

When one trial contributes multiple endpoint domains, can the system expose population, time-frame,
safety, and source reuse without treating structural identity as clinical comparability?

`clinical_benefit_risk_portfolio_stress` answers this narrower contract question. It revalidates one
multi-endpoint portfolio against its exact committed `ProgramState`, enumerates every unordered pair
of endpoint domains represented in the same trial, and rejoins each endpoint to its population and
safety ledger records. It computes no combined clinical result.

## Why pairwise stress is needed

A portfolio-level unique count reveals repeated trials and safety units, but it does not show which
endpoint-domain pairs create the reuse. The same trial can contain:

- distinct endpoint records linked to one analysis population and one safety record;
- endpoint records linked to different analysis-population identities;
- endpoint and safety windows that use different time-frame text;
- a repeated endpoint record relabeled as another family; or
- the same source artifact reused across several domain rows.

The stress report materializes these relationships. For a trial represented in `k` endpoint
domains, it emits exactly `k * (k - 1) / 2` unordered pair cells. Portfolios with no same-trial pair
fail instead of producing an empty success artifact.

## Replayed context

Each side of a pair retains:

- synthesis, endpoint-family, trial, design, and endpoint identities;
- endpoint and safety fingerprints;
- exact analysis-population id and a canonical hash of the population record;
- endpoint and safety time-frame text;
- treatment phase and population-alignment hash when phase-bound metadata exists;
- safety-unit and safety-record identities; and
- source content hashes.

The compiler first performs full portfolio recompilation. It then resolves the exact endpoint,
population, and safety records from the committed state and reruns phase-bound population alignment.
Missing, ambiguous, rebound, or internally inconsistent links fail closed.

## Pair statuses

| Status | Structural meaning | Nonclaim |
| --- | --- | --- |
| `matched_structure` | Population record, endpoint time frame, declared phase, safety record, and safety time frame match exactly. | Does not establish a shared estimand, participant identity, endpoint exchangeability, or clinical comparability. |
| `phase_undeclared` | Other structural identities match, but both endpoint contexts lack phase-bound metadata. | Does not infer treatment phase from endpoint names or timing. |
| `heterogeneous_structure` | At least one explicit identity, phase, endpoint-window, or safety-window difference is present. | Describes a difference; it does not rank endpoint validity or importance. |

Multiple diagnostic codes are retained on one pair. A population mismatch therefore cannot hide an
endpoint-window mismatch, and an endpoint relabeling cannot hide undeclared phase metadata.

## Safety and source reuse

`shared_safety_unit=true` means that both endpoint domains reference the same fingerprint-bound
safety record. The pair contributes one safety-reuse relationship, not two independent safety
observations. `shared_safety_counted_as_independent` and `safety_independence_inferred` are fixed to
false.

Source overlap is reported separately as `exact`, `partial`, or `disjoint`. Exact overlap is useful
for detecting derivative double counting, but content-hash identity alone does not establish source
truth or participant-level dependence.

## Executable contract

```python
from agentic_drug_discovery import (
    clinical_benefit_risk_portfolio_stress_report_envelope,
    compile_clinical_benefit_risk_portfolio_stress_report,
    validate_clinical_benefit_risk_portfolio_stress_report,
)

stress_report = compile_clinical_benefit_risk_portfolio_stress_report(
    state,
    portfolio_spec,
    portfolio_report,
)
assert validate_clinical_benefit_risk_portfolio_stress_report(
    state,
    portfolio_spec,
    portfolio_report,
    stress_report,
) == ()
payload = clinical_benefit_risk_portfolio_stress_report_envelope(stress_report)
```

Machine contract:

- `rl_env/specs/clinical_benefit_risk_portfolio_stress_report.schema.json`

## Current synthetic result

The identity-closed synthetic execution adds a second endpoint and its supporting evidence through
the normal mapping and synthesis stage runners for two trials.

| Stress condition | Same-trial pairs | Matched | Heterogeneous | Shared safety | Exact source overlap |
| --- | ---: | ---: | ---: | ---: | ---: |
| Distinct endpoints, same population/window/phase | 2 | 2 | 0 | 2 | 2 |
| Distinct endpoints, changed population and endpoint window | 2 | 0 | 2 | 2 | 2 |
| One endpoint record relabeled across two domains | 2 | 0 | 2 | 2 | 2 |

The heterogeneity control records both `analysis_population_identity_mismatch` and
`endpoint_timeframe_mismatch` for each trial while preserving the shared safety unit. The relabeling
control retains `endpoint_record_reused` and the legacy fixture's
`treatment_phase_not_declared` code. A four-trial portfolio with no cross-domain trial overlap is
rejected because it cannot exercise the stated same-trial question.

## Boundary and next evidence step

These results validate structural accounting and failure preservation only. They do not validate the
synthetic endpoint labels or establish clinical comparability, efficacy, safety, utility, treatment
choice, or external generalization.

A public-source execution requires two independently reviewed endpoint mappings from the same trial,
exact population and estimand citations, and a declared safety-window relationship. Those reviewer
materials and any real stress report remain outside the public package until separate scientific,
privacy, governance, and release review.
