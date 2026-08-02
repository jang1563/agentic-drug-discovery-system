# Preregistered Pattern-Mixture Sensitivity Analysis

## Research Question

The preceding stress study shows that outcome-dependent evaluability can move an observed-data
estimate away from its population target even when cluster-aware uncertainty is calibrated for the
evaluable target. This layer asks a narrower question:

> Under a preregistered range of assumptions about favorable outcomes among unevaluable units,
> does a prediction-stratified pattern-mixture analysis recover the population metric without using
> latent labels as an operational input?

The implementation is in
`agentic_drug_discovery/clinical_outcome_pattern_mixture.py`. It is bound to an exact
`ClinicalOutcomeStressSimulationProtocol`, reuses the same deterministic outcome and evaluability
streams, and emits aggregate diagnostics only.

## Sensitivity Parameter

For binary outcome `Y` and evaluability indicator `R`, define within each preregistered prediction
stratum:

```text
log-IMOR = logit P(Y = 1 | R = 0) - logit P(Y = 1 | R = 1)
```

For observed favorable probability `p_obs` and declared value `delta`, the favorable probability
among unevaluable units is

```text
p_mis(delta) = exp(delta) * p_obs
               -----------------------------------
               1 - p_obs + exp(delta) * p_obs
```

If `q` is the observed evaluable fraction in that stratum, the model-implied population favorable
probability is

```text
p_pop(delta) = q * p_obs + (1 - q) * p_mis(delta)
```

`delta = 0` is the MAR reference within the declared prediction strata. Negative values posit less
favorable outcomes among unevaluable units; positive values posit more favorable outcomes. The
parameter is not identified by the observed outcome data and must not be fitted from latent labels.

## Why Prediction Strata Are Retained

The analysis does not collapse all forecasts into one favorable-rate estimate. Units are grouped by
their exact preregistered `(policy_a_probability, policy_b_probability)` pair; repeated pattern
slots with the same pair are combined. For every stratum and every grid value it retains only these
ephemeral counts during simulation:

- total units;
- evaluable units;
- favorable evaluable units.

The stratum-specific model-implied prevalence is transformed into the eight additive metrics used
by the outcome-design study, then weighted by the full stratum size. This preserves systematic
differences in policy predictions without exporting unit IDs, labels, cluster rosters, or replicate
records.

## Fail-Closed Support Contract

A replicate is not analyzed when a partially observed prediction stratum has either:

- no evaluable units; or
- only favorable or only unfavorable observed outcomes.

The second condition is deliberate. A finite log-odds shift cannot move an empirical probability
at exactly zero or one, so silently returning a fixed answer would make the sensitivity grid appear
more informative than the data support. Scenario evaluability probabilities must also be strictly
between zero and one so that the synthetic truth has a finite log-IMOR.

## Preregistered Gates

The protocol fixes:

- the exact stress-protocol fingerprint;
- a unique increasing log-IMOR grid containing zero;
- a Monte Carlo confidence level for Wilson bounds on simulation rates;
- a minimum analyzable-replicate rate;
- a maximum absolute bias for evaluable calibration and truth-aligned recovery; and
- a maximum width for the mean sensitivity curve's identification envelope.

Three questions are evaluated separately.

1. **Evaluable calibration:** Does the unadjusted estimate remain close to its evaluable truth?
2. **Truth-aligned recovery:** If the synthetic data-generating log-IMOR is supplied only for an
   evaluator-side recovery diagnostic, does the adjusted estimate recover the population truth?
3. **Population identification:** Does the preregistered mean sensitivity curve reach the
   population truth within the bias tolerance without exceeding the width gate?

A scenario meets its research target only if the grid brackets the true synthetic log-IMOR and all
three conditions pass. The true parameter is never used to select or narrow the operational grid.

## Point-Envelope Inclusion Is Not Coverage

For transparency, the report retains the fraction of simulated replicates whose point-estimate
envelope contains the fixed population truth. This rate is descriptive. Each envelope varies only
the missingness assumption and contains no sampling-uncertainty interval, so its inclusion rate is
not expected to equal the nominal confidence level and is not a pass/fail criterion.

The v1 report instead gates the Monte Carlo mean sensitivity curve and separately reports recovery
bias. Wilson bounds apply to simulation rates, not to the continuous bias or mean-envelope-width
gates in this artifact. The fingerprint-bound follow-on in
`docs/35_dependence_closed_pattern_mixture_uncertainty.md` now adds Monte Carlo bias bounds and
dependence-closed cluster-jackknife sampling intervals without changing this v1 claim boundary.

## Public Synthetic Study

The public protocol binds to stress protocol
`1d195038b03855af77d96c1ee9f98cc28c8671ae89e678c9e199423162fb53f1` and uses 1,000 replicates
per scenario. Its grid is:

```text
[-4.0, -3.0, -2.397895272798, -1.5, -0.75, 0.0, 0.75, 1.5, 3.0, 4.0]
```

The two informative-evaluability scenarios have true log-IMOR `-2.397895272798`, corresponding to
an informative missingness odds ratio of `0.090909090909`. The MCAR scenario has log-IMOR `0` and
odds ratio `1`.

| Scenario | Naive population bias, favorable rate | Naive evaluable bias | Truth-aligned population bias | Mean identification width | Analyzable rate |
|---|---:|---:|---:|---:|---:|
| Combined informative evaluability + hidden linkage | 0.165348 | -0.003171 | 0.001117 | 0.378106 | 1.000 |
| Hidden linkage under MCAR | -0.003253 | -0.003253 | -0.003323 | 0.238513 | 1.000 |
| Informative evaluability + independent nominal clusters | 0.164663 | -0.003855 | 0.000349 | 0.376581 | 1.000 |

All three public scenarios meet the preregistered aggregate research targets. This means the
matched synthetic study distinguishes the large population-target drift from the small
evaluable-target bias and demonstrates recovery when the correct identifying assumption is
represented. It does not establish that the public grid is plausible for a real clinical board.

## Machine Contracts

- `rl_env/specs/clinical_outcome_pattern_mixture_protocol.schema.json`
- `rl_env/specs/clinical_outcome_pattern_mixture_protocol.example.json`
- `rl_env/specs/clinical_outcome_pattern_mixture_report.schema.json`
- `rl_env/specs/clinical_outcome_pattern_mixture_report.example.json`
- `rl_env/specs/clinical_outcome_pattern_mixture_summary.schema.json`

The public report fingerprint is
`6a9376fb5c64fb449ee0972ea95430db780dfa6d830bf065b5996cb71092094f`.

## CLI

Run the exact public analysis:

```bash
adds-clinical-evidence analyze-pattern-mixture \
  --protocol rl_env/specs/clinical_outcome_pattern_mixture_protocol.example.json \
  --stress-protocol rl_env/specs/clinical_outcome_stress_simulation_protocol.example.json \
  --output /tmp/clinical_outcome_pattern_mixture_report.json
```

Validate by full deterministic replay:

```bash
adds-clinical-evidence validate-pattern-mixture \
  --report /tmp/clinical_outcome_pattern_mixture_report.json \
  --protocol rl_env/specs/clinical_outcome_pattern_mixture_protocol.example.json \
  --stress-protocol rl_env/specs/clinical_outcome_stress_simulation_protocol.example.json
```

Emit the compact review surface:

```bash
adds-clinical-evidence summarize-pattern-mixture \
  --report /tmp/clinical_outcome_pattern_mixture_report.json
```

## Methodological Context

- The National Academies report on
  [missing data in clinical trials](https://www.ncbi.nlm.nih.gov/books/NBK209900/) explains why
  assumptions for unobserved outcomes require sensitivity analysis rather than being verified from
  observed data alone.
- A general method for
  [missing binary outcomes in randomized trials](https://pmc.ncbi.nlm.nih.gov/articles/PMC4241048/)
  demonstrates interpretable sensitivity analysis over assumptions about unobserved binary
  outcomes.
- Work on binary missing outcomes in network meta-analysis describes the
  [informative missingness odds ratio](https://pmc.ncbi.nlm.nih.gov/articles/PMC7792003/) as a
  pattern-mixture sensitivity parameter.

These references motivate the parameterization and claim boundary. They do not validate this
repository's synthetic grid, prediction strata, thresholds, or scenario probabilities.

## Follow-On Research

The immediate sampling-uncertainty milestone is implemented and documented in
`docs/35_dependence_closed_pattern_mixture_uncertainty.md`. Remaining work is outcome-blind
log-IMOR elicitation, unequal-cluster and multi-way-dependence methods, stratum-specific or partially
pooled sensitivity assumptions, and a locked multi-program endpoint/safety board with independent
adjudication.
