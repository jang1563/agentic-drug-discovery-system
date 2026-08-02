# Prospective Clinical Outcome Design Simulation

Status: executable synthetic design study; no real board threshold selected

## Research Question

The CR1 layer in `docs/31_cluster_robust_clinical_outcome_uncertainty.md` deliberately
withholds intervals when the board has too few evaluable clusters, one cluster contributes too
much of the evaluable sample, or a metric has zero observed cluster variance. Those safeguards
need board-specific design evidence rather than a universal cluster-count rule.

This module asks a prospective question:

> Under declared stage-by-endpoint prevalence, dependence, cluster-size, and evaluability
> scenarios, how often does the production CR1 implementation emit an interval, how wide is it,
> and how often does it cover the known target?

It is a design analysis, not a clinical result. It does not ingest real outcomes, select a gate
automatically, or modify the uncertainty protocol.

## Public Contracts

| Artifact | Role |
|---|---|
| `ClinicalOutcomeDesignSimulationProtocol` | Freezes the seed, data-generating process, Monte Carlo precision, fixed stage-by-endpoint scenarios, and candidate cluster gates. |
| `ClinicalOutcomeDesignSimulationReport` | Retains analytic truths, aggregate replicate diagnostics, IID reference behavior, CR1 candidate-gate behavior, and fixed claim-boundary flags. |
| `clinical_outcome_design_simulation_summary(...)` | Projects the report into a compact scenario/gate comparison with coverage, yield, width, bias, and status counts. |

Strict readers verify the envelope SHA-256, reject duplicate JSON keys and non-finite numbers,
and rebuild typed records with closed-field parsing. Full validation reruns every seeded replicate
and compares the complete aggregate report.

The implementation bounds scenario count, gate count, units, replicates, seed range, and total
work. Scenario RNG streams are independently derived from the master seed and scenario content,
so adding another canonical scenario does not perturb an existing stream.

## Scenario Definition

Each scenario declares:

- one fixed `stage × endpoint_family` design cell;
- an exact non-increasing cluster-size vector;
- marginal favorable prevalence `p`;
- intracluster correlation `rho`;
- MCAR evaluability probability;
- a classification threshold;
- two equal-length, outcome-independent probability patterns.

Every cluster size must be divisible by the prediction-pattern length. The same pattern is
repeated within every cluster, preserving the same expected forecast composition across clusters
even when their sizes differ.

## Exchangeable Binary Generator

For cluster `g`, let `S_(j-1)` be the number of favorable outcomes among its first `j-1` units.
The next binary outcome is drawn with probability

```text
P(Y_gj = 1 | history)
  = [p(1 - rho) + rho S_(j-1)] / [(1 - rho) + rho(j - 1)]
```

This is the beta-Bernoulli predictive representation of a beta-binomial model. It has marginal
prevalence `p` and exchangeable pairwise ICC `rho`; `rho = 0` reduces to independent Bernoulli
draws. It uses only the seeded MT19937 `random()` stream rather than runtime distribution helpers.

Evaluability is then drawn independently for each unit. Outcomes from non-evaluable units remain
part of the latent cluster process but do not enter metrics, matching an MCAR observation model.

## Analytic Estimands

Let `q_aj` and `q_bj` be the fixed probability patterns, `t` the classification threshold, and
the overbar denote the pattern mean. The simulator knows these targets before any replicate:

```text
favorable rate     = p
Brier(q)            = mean(q^2 - 2pq + p)
calibration(q)      = mean(q) - p
accuracy(q)         = mean(1[q >= t] p + 1[q < t] (1 - p))
Brier difference    = mean(q_b^2 - q_a^2 - 2p(q_b - q_a))
```

The fixed patterns deliberately test additive estimation, clipping, and paired covariance. They
are not a model of learned discrimination.

## Production Estimator Parity

Every replicate calls the same `_cluster_diagnostic(...)` and
`_cluster_robust_estimate(...)` functions used by the public clinical uncertainty evaluator.
There is no second simulation-only CR1 formula.

The IID diagnostic reference assigns each evaluable unit to its own cluster and uses the same
normal-mean interval machinery. It isolates the cost of ignoring declared dependence, but it is
not an acceptable analysis for a clustered board.

The report covers the eight additive targets implemented in the uncertainty layer:

- observed favorable rate;
- policy A and B Brier scores;
- policy A and B calibration-in-the-large;
- policy A and B threshold accuracy;
- paired Brier difference, `B - A`.

## Gate Evaluation

A candidate gate contains a minimum evaluable-cluster count and maximum evaluable-cluster share.
For every metric and gate, the report includes:

- point-estimate count, bias, RMSE, and empirical standard deviation;
- emitted-interval count and Wilson-bounded interval yield;
- covered-interval count and Wilson-bounded conditional coverage;
- mean reported standard error and interval width;
- mean reported-SE to empirical-SD ratio;
- all five production status counts.

The protocol declares a coverage tolerance and minimum interval yield. A gate's
`design_target_met` flag is true only when **every** metric satisfies both conditions using the
lower Monte Carlo Wilson bound:

```text
coverage lower bound >= confidence level - coverage tolerance
interval-yield lower bound >= minimum interval yield
```

This is a conservative screening rule for declared scenarios. It is not an automatic gate
selection rule, and it does not compare or rank gates outside those scenarios.

## Synthetic Example Finding

The checked-in example uses 300 replicates, 95% CR1 intervals, 95% Monte Carlo Wilson bounds, an
87% lower-bound coverage target, and an 80% lower-bound yield target.

| Scenario | `G / N` | ICC | Max share / effective `G` | IID favorable-rate coverage | CR1 favorable-rate coverage | Gate result |
|---|---:|---:|---:|---:|---:|---|
| balanced-12-moderate-icc | 12 / 48 | 0.10 | 0.083 / 12.00 | 0.907 | 0.913 | Both gates emit all intervals, but the worst metric's coverage lower bound is 0.861; neither passes. |
| balanced-24-low-prevalence | 24 / 96 | 0.05 | 0.042 / 24.00 | 0.917 | 0.940 | Both gates emit all intervals and pass all declared targets. |
| imbalanced-12-moderate-icc | 12 / 64 | 0.10 | 0.312 / 7.11 | 0.840 | 0.840 under the 0.40 gate | The 0.25 share gate emits in only 5/300 replicates; neither gate passes. |

These values are reproducible synthetic observations, not threshold recommendations. In
particular, the imbalanced design shows why raw cluster count alone is insufficient: 12 declared
clusters correspond to an effective count of only 7.11 before MCAR attrition.

The research test separately stresses 30 balanced clusters with ICC 0.20. In its fixed seeded run,
IID favorable-rate coverage is below 0.85 while CR1 coverage is above 0.93 and the CR1 interval is
wider. The assertion intentionally tests the direction and practical separation, not one exact
Monte Carlo percentage.

## CLI

```bash
adds-clinical-evidence simulate-uncertainty-design \
  --protocol prospective-design-protocol.json \
  --output aggregate-design-report.json

adds-clinical-evidence validate-uncertainty-design \
  --report aggregate-design-report.json \
  --protocol prospective-design-protocol.json

adds-clinical-evidence summarize-uncertainty-design \
  --report aggregate-design-report.json
```

Writes are atomic and refuse replacement unless `--force` is supplied. Validation without the
protocol checks envelope integrity and all aggregate typed invariants; validation with the
protocol performs full seeded replay.

## Machine Contracts

- `rl_env/specs/clinical_outcome_design_simulation_protocol.schema.json`
- `rl_env/specs/clinical_outcome_design_simulation_report.schema.json`
- `rl_env/specs/clinical_outcome_design_simulation_summary.schema.json`

The adjacent protocol and report examples contain only synthetic design parameters and aggregate
simulation results. No replicate labels, unit IDs, cluster IDs, real outcomes, or automatic gate
selection are published.

## Methodological Context

- Hong, Lim, and Bae's 2026
  [clustered prediction-performance framework](https://arxiv.org/abs/2606.03656)
  links cluster-robust intervals, paired comparisons, simulation, and prospective sample-size
  design; its small-cluster results also caution against treating asymptotic CR inference as
  automatically calibrated.
- Li and Redden's
  [small-sample sandwich simulation](https://pmc.ncbi.nlm.nih.gov/articles/PMC4268228/)
  uses beta-binomial binary outcomes parameterized by marginal prevalence and ICC to study
  clustered finite-sample behavior.
- Rutterford, Copas, and Eldridge's
  [cluster-trial sample-size review](https://doi.org/10.1093/ije/dyv113)
  emphasizes that unequal cluster sizes and ICC must be considered prospectively rather than
  replacing the design with a total-unit count.

These sources motivate the design dimensions. They do not validate this repository's scenarios
or select a universal gate.

## Next Research Step

Before a real outcome window opens:

1. Elicit plausible prevalence, ICC, evaluability, and cluster-size ranges from outcome-blind
   pilot evidence and the private dependence-manifest construction process.
2. Add stress scenarios for informative missingness, prevalence heterogeneity, cluster loss, and
   plausible cross-cluster leakage.
3. Increase Monte Carlo replicates until target decisions are stable at the declared Wilson
   precision.
4. Document why the chosen gate balances interval reliability and reportable-board yield for each
   fixed stage-by-endpoint cell.
5. Transfer the selected values into a new public `ClinicalOutcomeUncertaintyProtocol` before
   accepting policy submissions.
