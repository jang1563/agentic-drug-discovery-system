# UC Maintenance Risk-Difference Replication

Date: 2026-08-20
Status: completed public-source contract replication; not a therapeutic conclusion

## Research Question

Can the clinical provider preserve a primary maintenance endpoint reported as an absolute
percentage-point difference, keep candidate/comparator sign and units explicit, align posted
serious-safety summaries by role, and replay the result without importing raw source payloads into
the public repository?

The selected case is [ClinicalTrials.gov NCT01458574](https://clinicaltrials.gov/study/NCT01458574?tab=results),
a completed phase 3 ulcerative-colitis maintenance study. Tofacitinib identity is bound to
[ChEMBL CHEMBL221959](https://www.ebi.ac.uk/chembl/explore/compound/CHEMBL221959) through the
registry intervention aliases `CP690,550` and `CP-690,550`.

## Selection Audit

Six public ClinicalTrials.gov records were screened under one fixed contract. Selection required a
posted primary maintenance remission endpoint, an explicit percentage-point effect label,
candidate-then-comparator sign binding, exact endpoint/safety arm identities, and role-wise
endpoint/safety denominator agreement.

| Trial | Disposition | Decisive boundary |
| --- | --- | --- |
| `NCT01458574` | Selected | Primary Week 52 maintenance remission; explicit `Difference in percentage`; 198/198 endpoint and safety denominators in both selected roles |
| `NCT01647516` | Excluded | Week 32 maintenance remission is secondary; selected endpoint and maintenance-safety denominators differ |
| `NCT00783718` | Excluded | Maintenance safety pools vedolizumab schedules and additional populations; effect sign is not candidate-first in the posted group order |
| `NCT02407236` | Deferred | `Adjusted treatment difference` does not state the scale in the parameter label |
| `NCT02819635` | Excluded | Protocol maintenance arm combines assignments; endpoint and safety populations differ materially |
| `NCT03945188` | Deferred | Week 52 is a treat-through endpoint rather than an explicit phase-bound maintenance re-randomization; endpoint/safety denominators differ |

The machine-readable reason codes and source hashes are in
`docs/uc_maintenance_risk_difference_validation_snapshot.json`.

## Executed Result

The exact official API snapshot was captured outside Git at registry version `2026-08-20` and
verified against a reviewer-authored job. The public repository retains hashes and bounded results,
not the source bytes, review job, manifest, or run package.

| Field | Verified value |
| --- | --- |
| Candidate / comparator | Tofacitinib 5 mg BID / placebo |
| Primary endpoint | Percentage of participants in remission at Week 52 |
| Descriptive endpoint values | 34.3% (198) / 11.1% (198) |
| Registry effect | 23.2 percentage points, 95% CI 15.3 to 31.2, p `<0.0001` |
| Canonical effect | `risk_difference`, `higher_is_better`, null 0 |
| Serious-event summaries | 10/198 / 13/198 |
| Population alignment | Endpoint 396; safety 396; role-wise counts match; participant identity not inferred |
| Replay | `committed`, `promoted`, recommended `advance` to `regulatory_postmarket` |

| Artifact | SHA-256 |
| --- | --- |
| Exact source JSON | `b36fe4657f28c1f631d85d15f2e9357a348329c924ff754ca0abb5c17db930da` |
| Sanitized provider output | `0ec1c6a00e750a28c7375824ebb8f85fb669f4866e481a8f01b86ee4dae0dc17` |
| Compiled manifest | `5fc323e6fcf3002da32ac0c0f32da7ea500c0e2501d001c62b375da1f2b31adb` |
| Compile review | `d428f0017cb84c1c0de8e467b51fd7cb0abf1772b601bc8a322ee47e0c57a336` |

## Implemented Contract

The shared effect layer now distinguishes ratio effects, whose null is 1, from
`risk_difference`, whose null is 0. Supported risk-difference registry labels are deliberately
narrow: `Difference in percentage`, `Risk Difference (RD)`, `Risk Difference`, and
`Adjusted risk difference (%)`.

For `risk_difference`, the provider additionally requires:

- a bounded participant-, patient-, or subject-proportion percent unit, or bare percent unit;
- endpoint-declared `higher_is_better` or `lower_is_better` direction;
- candidate followed by comparator in the bound analysis group order;
- a finite ordered interval containing the estimate; and
- exact source agreement for the estimate, confidence interval, p-value, arms, and denominators.

The semantics propagate through extraction, promotion, endpoint mapping, typed study records, and
non-pooled descriptive synthesis. Public mapping and synthesis schemas accept the new measure.
The downstream clinical evidence tensor now accepts risk differences under a separate
percentage-point CI-width threshold. It still rejects a synthesis when the matching scale-specific
threshold is absent and never applies log-ratio precision to an additive interval.

## Interpretation Boundary

This replication shows that the software can preserve and replay one independent primary
maintenance result on an additive scale. It does not reproduce the estimate from participant-level
data, establish safety causality, infer clinical acceptability, or recommend treatment.

This is also not same-candidate cross-trial replication: the prior public UC work used ozanimod,
whereas this study uses tofacitinib. No cross-candidate synthesis or pooling was performed. The
additive decision policy is implemented and adversarially tested, but this one-trial replication is
not duplicated to satisfy the tensor's two-source minimum.
