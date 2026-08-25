# Cross-Disease Harmonization Robustness

Status: exact public-source execution completed on 2026-08-25

Scope: two source-disjoint, same-candidate-within-disease trial cohorts spanning rheumatoid
arthritis (RA) and ulcerative colitis (UC), compared as payload-free mechanical diagnostics

## Research question

Do the blocker patterns from the 35-pair olokizumab RA graph persist in another disease and trial
architecture, or are they artifacts of one registry pair?

The replication uses the complete posted-outcome Cartesian graph for two ozanimod/RPC1063 UC
trials, [NCT01647516](https://clinicaltrials.gov/study/NCT01647516?tab=results) and
[NCT02435992](https://clinicaltrials.gov/study/NCT02435992?tab=results). The UC cohort has 10 by 11
posted outcomes, producing 110 pairs. It is compared with the existing 5 by 7 olokizumab RA graph,
which has 35 pairs. The candidates differ across diseases; "same-candidate" applies independently
within each disease cohort and does not assert a shared intervention across RA and UC.

No endpoint pair was sampled, approved, excluded, pooled, or assigned to an endpoint family.

## Exact UC execution

The ClinicalTrials.gov API responses were captured on 2026-08-25. Current response bodies did not
contain a `versionHolder` field, so the inventory version records the capture date and the exact
source bytes are bound by SHA-256. Raw responses, source bundles, inventories, and the 110-pair
candidate packet remain external.

| Trial | Source SHA-256 | Inventory SHA-256 | Protocol outcomes | Posted outcomes | Exact lexical links | Safety records | Group-level safety statistics |
|---|---|---|---:|---:|---:|---:|---:|
| `NCT01647516` | `71ed6feb2d11e4c8d8cd82ca1bbfa7baf619d0b2f403763d38bfadeed07c4d89` | `5e72cff3475938547c5e6edbf608458dadba027811960a5fd76797825bb6ad2a` | 10 | 10 | 10 | 50 | 450 |
| `NCT02435992` | `5cfb559f2b89bfefa4004b8a8ab7ca5561389a882ff70f205fda5ce34d3faf07` | `07ef6bbb32be00708f27671c453f9fad7bee58076abd1052b681cce9b96d254a` | 11 | 11 | 11 | 56 | 280 |

Every posted outcome reconciled to one exact protocol title/time-frame candidate. All 110
cross-trial pairs nevertheless required source completion because neither side supplied a
dispersion type. This separates successful within-trial record linkage from cross-trial field
completeness.

## Cross-cohort result

Every rate below retains its own denominator. The robustness compiler does not sum, weight,
average, or rank the cohorts.

| Review route | RA olokizumab | UC ozanimod | Cross-cohort status |
|---|---:|---:|---|
| Semantic endpoint | 35/35 | 110/110 | `saturated_all` |
| Source-field completion | 34/35 | 110/110 | `heterogeneous` |
| Within-trial reconciliation | 0/35 | 0/110 | `absent_all` |
| Title identity | 31/35 | 110/110 | `heterogeneous` |
| Time frame | 22/35 | 110/110 | `heterogeneous` |
| Outcome type | 10/35 | 27/110 | `heterogeneous` |
| Reporting status | 0/35 | 0/110 | `absent_all` |
| Estimand structure | 35/35 | 110/110 | `saturated_all` |
| Population | 10/35 | 110/110 | `heterogeneous` |
| Safety window | 35/35 | 110/110 | `saturated_all` |

Three routes are saturated in both cohorts, two are absent in both, and five vary. This is a
stronger result than repeating a single aggregate count: it identifies which routing behavior is
stable under a disease/trial-architecture change and which remains cohort-dependent.

Missingness is narrow rather than general. Title, time frame, outcome type, reporting status,
parameter type, unit, population-description hash, and safety time frame are observed on both
sides of every pair in both cohorts. Only dispersion-type missingness varies: 34/35 RA pairs and
110/110 UC pairs have at least one missing value.

| Structural disagreement | RA olokizumab | UC ozanimod | Cross-cohort status |
|---|---:|---:|---|
| Group count | 35/35 | 110/110 | `saturated_all` |
| Denominator count | 0/35 | 0/110 | `absent_all` |
| Class count | 0/35 | 33/110 | `heterogeneous` |
| Category count | 0/35 | 33/110 | `heterogeneous` |
| Measurement count | 35/35 | 33/110 | `heterogeneous` |
| Analysis count | 25/35 | 83/110 | `heterogeneous` |
| Analysis group-ID sets | 35/35 | 83/110 | `heterogeneous` |

Group-count disagreement saturates both cohorts while denominator-count disagreement is absent.
That combination warns against treating the saturated estimand route as a direct measure of
endpoint-local semantic difficulty. Trial-global arm layouts can route every pair even when a
more local endpoint property agrees.

## What is established

The implemented pipeline now supports an exact source-disjoint robustness comparison across two
diseases and 145 complete-graph pairs while preserving cohort-specific denominators. It detects
stable saturation, stable absence, exact non-boundary stability, and heterogeneous prevalence
without floating-point comparisons. It also fails closed on report hash mismatch, report reuse,
NCT overlap, denominator changes, unknown fields, duplicate JSON keys, and integrity mismatch.

The result does not establish endpoint equivalence, disease generalization, semantic-review
accuracy, efficacy, population exchangeability, comparative safety, benefit-risk, regulatory
readiness, or treatment choice. A saturated route can reflect a policy invariant, source
missingness, or trial-global structure. Human semantic review was unavailable and was not
simulated.

## Next research priority

The next high-value step is to decompose structural routing into:

1. trial-global disagreement that is constant across all endpoints in each trial;
2. endpoint-local disagreement that varies within at least one trial; and
3. missing or non-identifiable structure.

That decomposition should precede adding many more diseases. Otherwise a trial-global arm-count
difference can keep the estimand route at 100% and obscure whether the system has learned anything
about endpoint-local harmonization. A third disease cohort is most informative after this
decomposition is executable and preregistered.

Follow-up status: this priority is now implemented in
`docs/58_structural_disagreement_decomposition.md` for both exact RA and UC graphs.

## Machine contract and replay

- UC diagnostic spec: `docs/uc_ozanimod_harmonization_diagnostic_spec.json`
- UC diagnostic report: `docs/uc_ozanimod_harmonization_diagnostic_report.json`
- UC candidate packet SHA-256: `aaefafba4d1c4bfa10c5589ceb102fe866fc5ebe89530f7fc2580aed49245b22`
- UC report integrity SHA-256: `2edf2956e0f4fdf0b2de97bd1db95bd9b15b210910af812709181f9a74d13156`
- UC spec/report file SHA-256: `cc567d0cc2288438df866bf6dde25c3a32769f9c3f78287667f6733947133c1a` / `f77b8e8d68d4de86782a4b0b4c2024b35de5d2516e0e0544fac8662391d41b68`
- Robustness spec: `docs/ra_uc_harmonization_robustness_spec.json`
- Robustness report: `docs/ra_uc_harmonization_robustness_report.json`
- Robustness report integrity SHA-256: `53a0d589d745502e4a657937f9ab359b78302dc6b2887a2743962fffacca3af4`
- Robustness spec/report file SHA-256: `59a255d8a927ba1bc9f7b0d7e115c38bc9efa9874cbea77c10ec7d8f9b7030d7` / `b64899e8a46980b2c726b7747f0f7580e4720bc85ecec79d2f32a9fa05c27491`

Replay the UC diagnostic from the two exact external API responses:

```bash
PYTHONPATH=. python scripts/audit/compile_ozanimod_uc_harmonization_diagnostic.py \
  --nct01647516-source /external/NCT01647516.json \
  --nct02435992-source /external/NCT02435992.json \
  --spec-output /tmp/uc-spec.json \
  --report-output /tmp/uc-report.json
```

Compile the cross-cohort profile in either report order:

```bash
adds-pinned-ingestion benchmark-clinicaltrials-gov-harmonization-robustness \
  --spec docs/ra_uc_harmonization_robustness_spec.json \
  --diagnostic-report docs/ra_olokizumab_mtx_ir_harmonization_diagnostic_report.json \
  --diagnostic-report docs/uc_ozanimod_harmonization_diagnostic_report.json \
  --output /tmp/ra-uc-robustness-report.json
```
