# Dependence-Closed Pattern-Mixture Sampling Uncertainty

## Research Question

The preceding pattern-mixture study varies the identifying assumption for unevaluable binary
outcomes but reports point curves only. This layer asks the next empirical question:

> At every preregistered log-IMOR assumption, does a delete-one-cluster jackknife provide calibrated
> sampling uncertainty for the corresponding model functional, and does closing declared residual
> dependence repair the undercoverage caused by treating linked clusters as independent?

The implementation is in
`agentic_drug_discovery/clinical_outcome_pattern_mixture_uncertainty.py`. The protocol binds the
exact stress protocol, pattern-mixture protocol, and pattern-mixture report fingerprints. The
seeded analysis must reproduce the prior point curve before any interval result is accepted.

## Two Uncertainty Axes

The sensitivity grid and the jackknife interval answer different questions.

1. **Identification uncertainty:** Changing `delta` changes the assumed odds of a favorable outcome
   among unevaluable units relative to evaluable units.
2. **Sampling uncertainty:** At one fixed `delta`, the jackknife measures variation from sampling
   independent top-level analysis clusters.

For each prediction stratum, observed favorable probability `p_obs`, evaluable probability `q`, and
fixed log-IMOR `delta` define

```text
p_mis(delta) = exp(delta) * p_obs / (1 - p_obs + exp(delta) * p_obs)
p_model(delta) = q * p_obs + (1 - q) * p_mis(delta)
```

The eight metric-specific model functionals are obtained by applying the fixed prediction pattern
to `p_model(delta)` and weighting by full stratum size. Coverage at each grid value is evaluated
against that grid value's model functional. Population-truth coverage is a recovery diagnostic only
at the synthetic true log-IMOR, where the model functional and population truth coincide.

## Delete-One-Cluster Jackknife

Let `theta` be the full-sample prediction-stratified pattern-mixture estimate at one fixed log-IMOR.
For `G` declared analysis clusters, recompute the complete nonlinear estimator after removing each
cluster to obtain `theta_(-g)`. The variance estimator is

```text
theta_bar = sum_g theta_(-g) / G
V_jack = (G - 1) / G * sum_g (theta_(-g) - theta_bar)^2
SE_jack = sqrt(V_jack)
```

The interval is centered on the full estimate and uses the same normal critical-value convention as
the production CR1 layer. Bounds are clipped to the metric scale. This is a cluster jackknife over
the complete pattern-mixture functional, not a unit-level bootstrap and not a delta-method
linearization of the missingness adjustment.

## Fixed Analysis Modes

Every scenario is evaluated under both modes without automatic selection:

- `nominal_clusters`: delete one nominal cluster at a time;
- `dependence_closed_clusters`: delete one complete declared dependence block at a time.

The synthetic dependence blocks are evaluator-side oracle structure. They demonstrate the effect of
correct closure but do not discover hidden links. In a real board, the dependence manifest must be
frozen from provenance before outcome analysis.

The primary closure-response anchor is preregistered as `observed_favorable_rate`. Residual outcome
dependence directly acts on this metric. Other policy metrics remain fully calibrated and reported,
but their nominal-versus-closed variance contrast is descriptive because prediction-stratum
contrasts can cancel block covariance. When no hidden linkage is declared, all eight metrics must be
exactly identical across the two modes.

## Fail-Closed Contract

An interval is not emitted when any of these conditions holds:

- the declared analysis has fewer than the minimum number of clusters;
- the largest enrolled-unit cluster fraction exceeds the fixed dominance limit;
- a full-sample prediction stratum has no evaluable reference outcomes;
- a partially observed full-sample stratum has only one observed outcome class;
- any leave-one-cluster-out sample loses the same required support; or
- the jackknife standard error rounds to zero at reporting precision.

Point estimates can remain available when only the cluster or leave-one-out interval contract fails.
Every grid-metric cell retains canonical status counts, so absence of an interval is explicit.

## Preregistered Calibration Gates

The public protocol fixes:

- 95% sampling intervals and 95% Monte Carlo bounds;
- a model-functional coverage lower-bound target of `0.87`;
- an interval-yield Wilson lower-bound target of `0.95`;
- at least 8 analysis clusters;
- a maximum enrolled-unit cluster fraction of `0.15`;
- an RMS jackknife-SE to empirical-SD ratio between `0.80` and `1.20`;
- the inherited maximum absolute bias of `0.02`, assessed using a Monte Carlo confidence bound;
- at least `0.02` closure coverage gain at the primary hidden-linkage anchor; and
- at least a `1.05` closed-to-nominal RMS-SE ratio at that anchor.

For continuous summaries, the report retains sample standard deviations and normal Monte Carlo
bounds for mean bias and interval width. Binary interval yield and coverage retain Wilson bounds.
The dependence-closed research target requires every metric at every grid value to pass bias,
yield, model-functional coverage, and SE-calibration gates. Nominal-cluster passage is not required
when hidden linkage is declared.

## Public Synthetic Results

The public report contains 1,000 replicates per scenario and 240 dependence-closed grid-metric cells
across three scenarios.

| Scenario | Nominal minimum coverage lower | Closed minimum coverage lower | Closed SE-ratio range | Anchor coverage gain | Anchor closed/nominal SE ratio | Closed all-grid target |
|---|---:|---:|---:|---:|---:|---:|
| Combined informative evaluability + hidden linkage | 0.830760 | 0.874465 | 0.9445-1.0187 | 0.054 | 1.2546 | Pass |
| Hidden linkage under MCAR | 0.832876 | 0.888491 | 0.9650-0.9948 | 0.060 | 1.2396 | Pass |
| Informative evaluability + independent nominal clusters | 0.897175 | 0.897175 | 0.9536-1.0170 | 0.000 | 1.0000 | Pass |

All three scenario research targets pass. In the two hidden-linkage scenarios, the nominal analysis
misses the coverage target while dependence closure restores all-grid calibration. In the
independent scenario, both modes are exactly equal across every aggregate inference field. Interval
yield is 1.0 in all public cells, with a Wilson lower bound of `0.996173`.

These results support the narrow synthetic claim that the declared dependence block is the correct
resampling unit for this generator. They do not validate a real dependence manifest, log-IMOR grid,
clinical endpoint, safety definition, treatment effect, or benefit-risk decision.

## Machine Contracts

- `rl_env/specs/clinical_outcome_pattern_mixture_uncertainty_protocol.schema.json`
- `rl_env/specs/clinical_outcome_pattern_mixture_uncertainty_protocol.example.json`
- `rl_env/specs/clinical_outcome_pattern_mixture_uncertainty_report.schema.json`
- `rl_env/specs/clinical_outcome_pattern_mixture_uncertainty_report.example.json`
- `rl_env/specs/clinical_outcome_pattern_mixture_uncertainty_summary.schema.json`

The public protocol fingerprint is
`9152583c61349513987ef45d6553d9e2157b723dcc57e9640a26d8d4c498bea4`. The public report
fingerprint is `931b7bb9cc06f1949085e9763bb2f93671a8a29547c1036cc31d0245cc02b045`.

## CLI

Run the exact public analysis:

```bash
adds-clinical-evidence analyze-pattern-mixture-uncertainty \
  --protocol rl_env/specs/clinical_outcome_pattern_mixture_uncertainty_protocol.example.json \
  --pattern-mixture-protocol rl_env/specs/clinical_outcome_pattern_mixture_protocol.example.json \
  --stress-protocol rl_env/specs/clinical_outcome_stress_simulation_protocol.example.json \
  --output /tmp/clinical_outcome_pattern_mixture_uncertainty_report.json
```

Validate by complete seeded replay:

```bash
adds-clinical-evidence validate-pattern-mixture-uncertainty \
  --report /tmp/clinical_outcome_pattern_mixture_uncertainty_report.json \
  --protocol rl_env/specs/clinical_outcome_pattern_mixture_uncertainty_protocol.example.json \
  --pattern-mixture-protocol rl_env/specs/clinical_outcome_pattern_mixture_protocol.example.json \
  --stress-protocol rl_env/specs/clinical_outcome_stress_simulation_protocol.example.json
```

Emit the compact review surface:

```bash
adds-clinical-evidence summarize-pattern-mixture-uncertainty \
  --report /tmp/clinical_outcome_pattern_mixture_uncertainty_report.json
```

## Methodological Context

- A clustered pattern-mixture analysis for longitudinal cluster-randomized trials illustrates why
  missing-data assumptions and intracluster dependence must be handled together:
  <https://pmc.ncbi.nlm.nih.gov/articles/PMC5628153/>.
- A study of informative missingness odds ratios for binary outcomes motivates explicit,
  interpretable assumption grids rather than treating missing outcomes as ignorable:
  <https://pmc.ncbi.nlm.nih.gov/articles/PMC7792003/>.
- Work on weighted jackknife variance estimation for clustered data documents the importance of
  cluster size and influence for delete-cluster methods:
  <https://pmc.ncbi.nlm.nih.gov/articles/PMC10959512/>.

These references motivate the design. They do not validate this repository's generator, thresholds,
normal critical values, or synthetic result.

## Next Research Step

The next empirical layer should move from synthetic oracle closure toward a locked clinical board:

1. elicit endpoint- and safety-specific log-IMOR ranges before outcome access;
2. freeze provenance-derived dependence blocks across programs, trials, publications, sites, and
   shared control arms;
3. compare normal, small-cluster, weighted delete-cluster, and wild-cluster calibration under
   unequal and influential block sizes;
4. evaluate stratum-specific and partially pooled log-IMOR assumptions without outcome-driven grid
   selection;
5. add structured block loss, non-nested multi-way dependence, and adjudication-error stress; and
6. run a locked multi-program endpoint/safety harmonization board that carries both identification
   and sampling uncertainty into provenance-preserving benefit-risk synthesis.
