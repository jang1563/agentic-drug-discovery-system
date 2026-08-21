# Olokizumab RA Population-Stratified Transport Diagnostic

## Research question

Can the source-disjoint olokizumab Week-12 ACR20 evidence tensor be extended into a
population-aware analysis without pooling methotrexate-inadequate-response and
TNF-inhibitor-inadequate-response trials or implying that either represents an undeclared target
population?

The answer is now split deliberately:

- **Population stratification:** complete and exactly replayed.
- **Transport effect estimation:** not estimable from the available aggregate evidence.

## Contract

`agentic_drug_discovery/clinical_population_transport.py` implements a reviewed, fail-closed
diagnostic. Its input contract is frozen in
`rl_env/specs/clinical_population_transport_spec.example.json` and binds each declaration to:

- the exact non-pooled `BenefitRiskSynthesisRecord`;
- trial, design, endpoint, and analysis-population identifiers;
- a source document whose SHA-256 is already committed by the synthesis;
- an exact ClinicalTrials.gov JSON field and field-level SHA-256;
- one reviewer-declared prior-therapy stratum.

The compiler performs no free-text similarity matching and does not infer eligibility classes. It
verifies the declared source field against the exact source bytes, then preserves the reviewed
classification. Project-internal approval is sufficient only for this descriptive run and is not
represented as independent external scientific review.

## Exact execution

The diagnostic replayed the excluded source and state bundle used for the prior additive tensor.
The exact report is public at `docs/ra_olokizumab_population_transport_report.json`.

| Trial | Reviewed prior-therapy stratum | Week-12 ACR20 risk difference (97.5% CI) | Serious events, candidate vs comparator | Within-stratum trials |
|---|---|---:|---:|---:|
| `NCT02760407` | Methotrexate inadequate response | 0.270 (0.183 to 0.352) | 20/477 vs 12/243 | 1 |
| `NCT02760433` | TNF inhibitor inadequate response | 0.190 (0.030 to 0.337) | 6/160 vs 0/69 | 1 |

The analysis-population descriptions in both registry result records are the same generic ITT
definition and therefore have the same description hash:
`64200bf50da664863bb0d69cf8147cfab827f75dafb8926407150d4ae51f92dc`.
That equality does not erase the trial-level treatment-history boundary. The official-title fields
supporting the reviewed contexts have different hashes and remain attached to different source
documents:

| Trial | Source SHA-256 | Reviewed source-field SHA-256 |
|---|---|---|
| `NCT02760407` | `62415b71d08c8d5ccbe0b03be45bad4ad8bd734d43de461be52278314fbb59d8` | `9da94dc8b9604e29c6f8805f4344f3d6cff0130741665a9b8f8db4e39b9f495b` |
| `NCT02760433` | `b087ef355db040907d7ae81c34b34fec7f9b4743df7414c8f519eee6e3abc051` | `fe68e108b8df5ea259facf89c02d617e32457722b4e93e13c267372f300b3e7d` |

The exact reviewed-spec fingerprint is
`d9b9dfc38843a603d473a619a70ce8da7d92e1561d8207a15871fac5033540e1`.

The exact synthesis fingerprint is
`4c67340fc67cdc4ae3f71fa39028760e779ead07c2f119e4699769c6069d2be9`, and the public report
integrity hash is
`c09f425ea93b70549168f54044ec7e31eb80b0696106c2a90d02e9971a7abe44`.

## Result

The machine status is
`descriptive_stratification_complete_transport_not_estimable`. The report records seven explicit
blockers:

1. No target population is declared.
2. The reviewed prior-therapy strata differ.
3. Each stratum has only one trial.
4. Only aggregate registry results are available.
5. Individual-level covariate distributions are unavailable.
6. No transport model is preregistered.
7. Risk of bias has not been assessed in this diagnostic.

Consequently, `pooling_performed`, `cross_stratum_effect_contrast_computed`,
`population_homogeneity_inferred`, `population_exchangeability_inferred`, and
`transport_effect_estimated` are all `false`. The two trial effects are retained side by side; their
difference is not interpreted as effect modification.

## Verification surface

- Spec schema: `rl_env/specs/clinical_population_transport_spec.schema.json`
- Report schema: `rl_env/specs/clinical_population_transport_report.schema.json`
- Exact reviewed spec: `rl_env/specs/clinical_population_transport_spec.example.json`
- Exact public report: `docs/ra_olokizumab_population_transport_report.json`
- Compiler and strict readers: `agentic_drug_discovery/clinical_population_transport.py`
- Rebinding, source-tampering, field-hash, target-overclaim, and round-trip tests:
  `tests/test_clinical_benefit_risk_synthesis.py`

The report exposes bounded aggregate values, identifiers, field pointers, and hashes. Raw registry
bytes, reviewer job text, complete states, and decision packages remain outside the public release.

## Interpretation boundary

This milestone strengthens population provenance and makes a non-estimable transport question
auditable. It is not a meta-analysis, adjusted indirect comparison, causal transport analysis,
comparative-safety conclusion, efficacy validation, clinical acceptability judgment, or treatment
recommendation.

The same-stratum replication branch is now complete for the MTX-inadequate-response context; see
`docs/48_ra_olokizumab_mtx_ir_same_stratum_replication.md`. That follow-on removes the distinct-
strata and no-within-stratum-replication blockers, but it does not retrofit exchangeability or a
transport effect into this original cross-stratum report. Independent scientific review, a target
population, individual-level or transport-compatible covariates, a preregistered transport model,
and risk-of-bias assessment remain separate requirements.
