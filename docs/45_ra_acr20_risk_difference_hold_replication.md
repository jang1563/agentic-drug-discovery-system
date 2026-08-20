# Rheumatoid-Arthritis ACR20 Risk-Difference HOLD Replication

Date: 2026-08-20
Status: completed public-source contract replication; not a therapeutic conclusion

## Research Question

Can the clinical provider preserve a source-pinned percentage-point efficacy result in a second
immune-inflammatory disease and retain an uncertain result as evidence without advancing the
workflow?

The selected case is [ClinicalTrials.gov NCT00383188](https://clinicaltrials.gov/study/NCT00383188?tab=results),
a completed phase 2 rheumatoid-arthritis study. PH-797804 identity is bound to
[ChEMBL CHEMBL1088751](https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL1088751), and disease
identity is bound to `MONDO:0008383`.

## Selection Audit

Five official records were examined under the bounded additive-effect contract. Selection required
a full source chronology, a posted primary bounded-percent endpoint, candidate-then-comparator
analysis order, a typed p-value, and exact endpoint and serious-safety arm identities.

| Trial | Disposition | Decisive boundary |
| --- | --- | --- |
| `NCT00383188` | Selected | Primary ACR20 at Week 12; candidate-first `Difference in percentage`; exact endpoint and SAE group identities |
| `NCT02899988` | Excluded | Mirikizumab PASI90 analysis lists placebo before candidate; additive sign is not inferred |
| `NCT03482011` | Excluded | Mirikizumab PASI90 analysis lists placebo before candidate; candidate endpoint and safety denominators also differ |
| `NCT01039688` | Deferred | Tofacitinib ACR70 is candidate-first, but source primary-completion chronology is month-precision only |
| `NCT03926195` | Deferred | Filgotinib difference analysis has no posted p-value required by the bounded provider contract |

Machine-readable reason codes and source hashes are in
`docs/ra_acr20_risk_difference_validation_snapshot.json`.

## Executed Result

The exact official API snapshot was captured outside Git at registry version `2026-08-20` and
verified against a reviewer-authored job. The repository retains hashes and bounded aggregates,
not source bytes, review jobs, manifests, or run packages.

| Field | Verified value |
| --- | --- |
| Candidate / comparator | PH-797804 0.5 mg / placebo |
| Primary endpoint | ACR20 response at Week 12 |
| Descriptive endpoint values | 39.13% (69) / 31.08% (74) |
| Registry effect | 8.05 percentage points, 95% CI -7.565 to 23.664, p = 0.3131 |
| Additive CI width | 31.229 percentage points |
| Canonical effect | `risk_difference`, `higher_is_better`, null 0 |
| Serious-event summaries | 2/69 / 1/75 |
| Replay | `committed`, `promoted`, recommended `hold`; stage remains `clinical_strategy` |

| Artifact | SHA-256 |
| --- | --- |
| Exact source JSON | `399f4d167ff53d8207f1b5c5cad5b70adea5c4d2d0377b41cb6ee8c0c618676a` |
| Sanitized provider output | `4615b147bd5e5c067a6fe7b4102fb0f3212b13b874cbe3cde2714eb71a72a20b` |
| Compiled manifest | `e1f65293e927ace4aa4c61787f5d8cb5869f567b0f8d4dba32af9311050bed00` |
| Compile review | `382a91736859e9d2c41b21ca07f46b4ea780df2d3d55a11e241571c0a6b62ff6` |

## Additive Decision Contract

The decision tensor now uses scale-specific precision rather than applying log-ratio uncertainty to
an additive effect:

- hazard, odds, and risk ratios use `maximum_log_effect_ci_width`;
- percentage-point risk differences use
  `maximum_risk_difference_ci_width_percentage_points`;
- a synthesis is rejected when its matching policy threshold is absent;
- risk-difference cells retain endpoint favorable direction and raw percentage-point CI width;
- ratio package serialization and existing public fingerprints remain unchanged.

This real execution stops at one eligible source-pinned RA trial. It is not duplicated to satisfy
the tensor's minimum of two source-disjoint trials. Additive tensor and bounded-VOI behavior are
verified by adversarial compiler tests, while a real RA multi-trial tensor remains open work.

## Interpretation Boundary

The run demonstrates correct retention of uncertainty: a structurally valid result is committed,
but its confidence interval crosses the additive null and the workflow does not advance. The
observed serious-event risks are descriptive, the endpoint and safety denominators differ by one in
the comparator role, and participant identity is not inferred. No pooling, causal safety claim,
clinical acceptability judgment, or treatment recommendation is made.
