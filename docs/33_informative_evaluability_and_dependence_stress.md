# Informative Evaluability and Dependence-Closure Stress

Status: executable synthetic stress study; diagnostic only, with no missing-data correction

## Research Question

The prospective simulator in
`docs/32_prospective_clinical_outcome_design_simulation.md` assumes missing completely at random
and independent top-level clusters. Those assumptions separate the first design problem cleanly,
but two distinct failures can remain in a real evidence board:

1. outcome evaluability can depend on the latent favorable/unfavorable label, changing the target
   represented by complete records; and
2. nominal clusters can remain dependent because a trial, site network, registry, source process,
   or other shared origin crosses nominal cluster boundaries.

This module asks:

> Can the production CR1 path distinguish estimand drift caused by outcome-dependent
> evaluability from interval miscalibration caused by an incomplete dependence partition?

It does so by evaluating the same estimates against two analytic targets and under two fixed
cluster assignments. It does not infer a missingness mechanism, discover hidden links, or correct
a population estimand.

## Fixed Comparison

Every protocol must retain the complete comparison matrix:

| Axis | Level 1 | Level 2 |
|---|---|---|
| Estimand target | `population` | `evaluable` |
| Analysis mode | `nominal_clusters` | `dependence_closed_clusters` |

The engine does not permit dropping a level. A scenario can make the two levels coincide, which
creates useful negative controls:

- equal favorable/unfavorable evaluability probabilities make the two estimands equal;
- singleton dependence blocks make the two cluster analyses equal.

## Stress Data-Generating Process

Each scenario declares a non-increasing nominal cluster-size vector and a canonical partition of
nominal cluster indices into dependence blocks. A block may contain one or several nominal
clusters, but every nominal cluster must occur exactly once.

For dependence block `b`, the binary labels follow one Polya urn. If `S_(t-1)` is the number of
favorable outcomes among the first `t-1` units in that block, then

```text
P(Y_bt = 1 | history)
  = [p(1 - rho) + rho S_(t-1)] / [(1 - rho) + rho(t - 1)]
```

This produces marginal favorable prevalence `p` and exchangeable pairwise correlation `rho`
across all units in the block. When a block contains several nominal clusters, those clusters are
dependent by construction. Different blocks use independent urn histories.

Evaluability is then drawn from a separate deterministic RNG substream:

```text
P(R = 1 | Y = 1) = r1
P(R = 1 | Y = 0) = r0
```

Separate outcome and evaluability substreams make the simulation mechanism explicit and prevent
changes in one component from silently redefining the other random stream.

## Analytic Targets

The expected evaluable fraction is

```text
q = p r1 + (1 - p) r0
```

and the favorable prevalence among evaluable units is

```text
p_evaluable = p r1 / q.
```

The `population` metric truths use `p`; the `evaluable` metric truths use `p_evaluable`. All eight
additive truths then use the equations in the v1 design simulator:

```text
favorable rate     = prevalence
Brier(s)           = mean(s^2 - 2 prevalence s + prevalence)
calibration(s)     = mean(s) - prevalence
accuracy(s)        = mean(1[s >= t] prevalence + 1[s < t] (1 - prevalence))
Brier difference   = mean(s_b^2 - s_a^2 - 2 prevalence (s_b - s_a))
```

For every replicate, mode, gate, and metric, the estimator runs once. That same point estimate and
interval are added to both target accumulators. Therefore differences in bias, RMSE, and coverage
between targets are caused only by the declared estimand, not by two implementations or two
random samples.

## Dependence Analyses

`nominal_clusters` sends the nominal cluster IDs to the production
`_cluster_diagnostic(...)` and `_cluster_robust_estimate(...)` functions.

`dependence_closed_clusters` merges all nominal clusters in each declared block before calling the
same production functions. It is an oracle analysis because the synthetic generator supplies the
true block partition. The point estimate remains the evaluable-unit mean; only gate diagnostics,
cluster scores, standard errors, and intervals can change.

The expected signatures are:

| Stressor | Nominal population | Nominal evaluable | Closed population | Closed evaluable |
|---|---|---|---|---|
| Informative evaluability only | Biased/miscalibrated | Calibrated | Same as nominal | Same as nominal |
| Hidden linkage under MCAR | Undercovered | Undercovered | Calibrated | Same as population |
| Both stressors | Biased and undercovered | Undercovered | Still biased | Calibrated |

These are diagnostic signatures, not identification results. Observed data alone need not reveal
which stressor generated a failure.

## Exact Synthetic Finding

The checked-in study uses 1,000 replicates, 24 nominal clusters of 8 units, ICC `0.15`, 95% CR1
intervals, a coverage lower-bound target of `0.87`, and an interval-yield lower-bound target of
`0.80`. Hidden-linkage scenarios merge adjacent nominal clusters into 12 true blocks. Informative
scenarios use `p = 0.35`, `r1 = 0.90`, and `r0 = 0.45`, giving
`p_evaluable = 0.518518518519`.

The table reports favorable-rate coverage for the first gate; the all-metric target flag has the
same result for both checked-in gates.

| Scenario and mode | Population coverage / target | Evaluable coverage / target |
|---|---:|---:|
| Informative only, nominal | `0.228` / fail | `0.935` / pass |
| Informative only, closed | `0.228` / fail | `0.935` / pass |
| Hidden linkage MCAR, nominal | `0.855` / fail | `0.855` / fail |
| Hidden linkage MCAR, closed | `0.923` / pass | `0.923` / pass |
| Combined, nominal | `0.271` / fail | `0.862` / fail |
| Combined, closed | `0.400` / fail | `0.914` / pass |

For hidden-linkage MCAR, the estimate is identical across modes while the nominal mean reported
standard error is smaller. For the combined scenario, closure repairs variance calibration for
the evaluable target but cannot remove selection bias relative to the population target. That is
the central separation this study is designed to preserve.

## Public Contracts

| Artifact | Role |
|---|---|
| `ClinicalOutcomeStressSimulationProtocol` | Freezes RNG streams, exact block partitions, evaluability probabilities, both analysis modes, both targets, scenarios, and candidate gates. |
| `ClinicalOutcomeStressSimulationReport` | Retains analytic target shifts, mode-specific structures and diagnostics, target-specific aggregate performance, and strict claim-boundary flags. |
| `clinical_outcome_stress_simulation_summary(...)` | Projects target-met gate IDs, evaluable-only passes, and dependence-closure recovery signatures without unit or replicate records. |

Strict readers reject duplicate JSON keys, non-finite values, unknown fields, non-canonical or
incomplete partitions, altered substream hashes, inconsistent analytic truths, target/mode
omission, status/count inconsistencies, and envelope tampering. Full validation reruns every
seeded replicate and compares the complete aggregate report.

The implementation also bounds scenarios, gates, units, replicates, seed range, prediction
patterns, and total simulation work.

## CLI

```bash
adds-clinical-evidence simulate-uncertainty-stress \
  --protocol rl_env/specs/clinical_outcome_stress_simulation_protocol.example.json \
  --output aggregate-stress-report.json

adds-clinical-evidence validate-uncertainty-stress \
  --report aggregate-stress-report.json \
  --protocol rl_env/specs/clinical_outcome_stress_simulation_protocol.example.json

adds-clinical-evidence summarize-uncertainty-stress \
  --report aggregate-stress-report.json
```

Writes are atomic and refuse replacement unless `--force` is supplied. Validation without a
protocol checks integrity and aggregate invariants; validation with a protocol performs full
seeded replay.

## Machine Contracts

- `rl_env/specs/clinical_outcome_stress_simulation_protocol.schema.json`
- `rl_env/specs/clinical_outcome_stress_simulation_protocol.example.json`
- `rl_env/specs/clinical_outcome_stress_simulation_report.schema.json`
- `rl_env/specs/clinical_outcome_stress_simulation_report.example.json`
- `rl_env/specs/clinical_outcome_stress_simulation_summary.schema.json`

The report is aggregate-only. It contains no unit IDs, cluster IDs, replicate labels, real
outcomes, inferred missingness model, automatic gate selection, or automatic population-target
correction.

## Methodological Context

- Hossain, DiazOrdaz, and Bartlett's study of
  [missing binary outcomes in cluster-randomized trials](https://pmc.ncbi.nlm.nih.gov/articles/PMC5518290/)
  demonstrates that complete-record validity depends on the missingness mechanism, estimand, and
  analysis model rather than following from cluster adjustment alone.
- Turner et al. show that available-data GEE can be biased when outcomes are not MCAR and compare
  [weighted GEE with multilevel multiple imputation](https://doi.org/10.1177/0962280219859915).
  This stress module diagnoses the unweighted estimand split; it does not implement either
  correction.
- Desai, Bryson, and Robinson directly examine
  [cluster-membership misspecification](https://pubmed.ncbi.nlm.nih.gov/23220255/) for robust
  standard errors and motivate testing sensitivity to the declared cluster assignment.
- Cameron, Gelbach, and Miller's
  [multi-way clustering framework](https://www.nber.org/papers/t0327) establishes that one-way
  clustering does not generally absorb non-nested dependence along another dimension. The
  current block-closure study is narrower than a multi-way estimator.

These sources motivate the failure modes. They do not validate this repository's synthetic
parameters or imply that the oracle block partition is observable in practice.

## Next Research Step

The next methodological layer should move from diagnosis to preregistered sensitivity analysis:

1. add a selection-model or pattern-mixture sensitivity grid that does not require using latent
   labels in an operational correction;
2. add inverse-probability-weighted and augmented estimators only when their observability,
   positivity, nuisance-model, and cluster-robust variance contracts are explicit;
3. stress block-level cluster loss and structured prevalence heterogeneity;
4. add non-nested or multi-way dependence scenarios rather than representing every structure as
   one oracle partition;
5. require recovery tests to distinguish population-target identification assumptions from
   evaluable-target calibration.
