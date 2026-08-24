# Olokizumab RA MTX-IR Same-Stratum Replication

Date: 2026-08-20
Status: completed public-source workflow replication; transport effect remains not estimable

## Research question

Can the olokizumab Week-12 ACR20 evidence program replace a cross-population comparison with an
independent same-population-context replication, while retaining source-level effects and safety
aggregates without pooling?

The selected pair is
[NCT02760407](https://clinicaltrials.gov/study/NCT02760407?tab=results) and
[NCT02760368](https://clinicaltrials.gov/study/NCT02760368?tab=results). Both are completed phase 3
trials of olokizumab 64 mg every four weeks plus methotrexate versus placebo plus methotrexate in
rheumatoid arthritis inadequately controlled by methotrexate.

## Source and chronology contract

`NCT02760368` reports its primary completion date at month precision (`2018-08`). The provider
previously accepted only day-precision dates. The implementation now parses day, month, and year
precision separately and maps a partial registry period to its conservative period end for the
internal event date. It preserves all three facts in the sanitized record:

- source value: `2018-08`;
- source precision: `month`;
- normalized event boundary: `2018-08-31`;
- normalization rule: `conservative_period_end`.

The exact results-first-post date remains `2020-10-30`. A job that supplies any other day for the
month-precision completion date fails closed. Invalid calendar periods also fail closed. This
extends source coverage without inventing false day precision.

## Executed replication

Both source-pinned provider runs committed and promoted. The reviewer-declared mapping binds the
same candidate, dose cadence, comparator, endpoint family, endpoint time point, effect measure,
and prior-therapy stratum.

| Trial | Week-12 ACR20 | Source RD (97.5% CI) | CI width | Serious events |
| --- | ---: | ---: | ---: | ---: |
| `NCT02760407` | 342/479 vs 108/243 | 0.270 (0.183 to 0.352) | 16.9 pp | 20/477 vs 12/243 |
| `NCT02760368` | 100/142 vs 37/143 | 0.445 (0.318 to 0.552) | 23.4 pp | 8/142 vs 4/142 |

The synthesis contains two source-disjoint study cells and performs no pooling. Both source
benefit intervals remain positive on their registry-reported risk-difference scale. The observed
serious-event direction is lower in `NCT02760407` and higher in `NCT02760368`; the safety
collection text also differs. The decision tensor therefore remains `HOLD`, with
`higher_observed_serious_event_risk` as a blocking gap and `safety_timeframe_mismatch` as a
non-blocking descriptive gap. These are workflow signals, not comparative-safety conclusions.

## Population result

The exact reviewed spec is
`docs/ra_olokizumab_mtx_ir_replication_spec.json`, and the integrity-bound report is
`docs/ra_olokizumab_mtx_ir_replication_report.json`.

| Reviewed stratum | Trial support | Prior blocker | Result |
| --- | ---: | --- | --- |
| Methotrexate inadequate response | 2 | `no_within_stratum_replication` | removed |
| Cross-stratum comparability | one observed stratum | `distinct_reviewed_population_strata` | removed |

Five transportability blockers remain:

1. `target_population_not_declared`
2. `aggregate_registry_results_only`
3. `individual_level_covariates_unavailable`
4. `transport_model_not_preregistered`
5. `risk_of_bias_not_assessed`

Removing the two population-structure blockers does not make a transport effect estimable. The
report keeps `population_homogeneity_inferred`, `population_exchangeability_inferred`,
`pooling_performed`, `cross_stratum_effect_contrast_computed`, and `transport_effect_estimated`
equal to `false`.

## Provenance

| Artifact | SHA-256 |
| --- | --- |
| `NCT02760407` source | `62415b71d08c8d5ccbe0b03be45bad4ad8bd734d43de461be52278314fbb59d8` |
| `NCT02760368` source | `7d0f38ee584e2af66cc7b4ebec8d2cc8b86327183a887eba6c5ce1ff96a2d1e7` |
| `NCT02760368` sanitized provider output | `23da664d26b5a79bd79aee7e96b013d2288abec7d3b9b11867e027c359ecd8ee` |
| `NCT02760368` compiled manifest | `0a0e7042eee2aa2bac1672dc5eb121ed18722a659668a25a4015964224aae866` |
| `NCT02760368` compile review | `59e401244dcb6fbb921845d85802910e75eb4ad7509a4e8379ddf617847c9226` |
| Mapped state | `0c0218bade75fd55ef63a033271773899a9bb2cba2750ddd23b04b063b3c44c1` |
| Synthesized state | `3658e00ca1731e058404fcbc513124d12b5d6d80f7aa0d2a459f18499e95f3e1` |
| Decision package | `25a70f718033aa356baa5b7cc2fdda547b69467709d01828835f572176a9365d` |
| Run summary | `c4047b32278e4c3fe665ec586196c578e09d1d2ff35ae708baa2fb7b87fc8b9c` |
| Reviewed population spec | `fbebb8907f039bf0635224ab4e35ed493afe51f144d01011294f5d1c9db96d59` |
| Exact synthesis | `5b426483750f23a59a0fd5ff4ddba2897381371affbb7a0d3deb7fdde84d5634` |
| Population report integrity | `3102fa78eec99959e0a2b5025ec5232b7abb2e51c81065fd98be73ec36e7b2cd` |

Raw registry bytes, reviewer jobs, manifests, complete states, and the decision package remain
outside Git and Hugging Face. The public spec and report contain bounded declarations, aggregates,
identifiers, and hashes only.

## Interpretation boundary

This milestone establishes independent same-stratum contract replication for one aggregate
clinical endpoint. It is not a meta-analysis, causal transport analysis, participant-level
reanalysis, efficacy validation, comparative-safety finding, clinical acceptability judgment, or
treatment recommendation. The next feasible blocker-reduction study is a preregistered,
source-bound trial-level risk-of-bias assessment; target-population transport would additionally
require covariate and estimand information unavailable in these aggregate registry records.
