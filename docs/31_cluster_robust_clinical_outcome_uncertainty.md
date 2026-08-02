# Cluster-Robust Clinical Outcome Uncertainty

Status: executable synthetic research contract; no real dependence-audited board result yet

## Purpose

`docs/30_preregistered_clinical_outcome_evaluation.md` binds package-level probability forecasts
to independently curated endpoint and safety outcomes. Its Wilson intervals describe binary
event counts as if evidence units were independent. That assumption can fail when programs reuse
trial lineages, source artifacts, populations, sites, sponsors, or other infrastructure.

This layer adds preregistered dependence assignments and CR1 cluster-robust uncertainty without
changing the base outcome report. It does not relabel outcomes, refit policies, or convert
workflow decisions into clinical outcomes.

## Contracts And Visibility

| Artifact | Visibility | Role |
|---|---|---|
| `ClinicalOutcomeDependenceManifest` | Evaluator only | Exact evidence-unit-to-cluster assignments, construction-policy commitment, and independence-attestation commitment frozen before submissions. |
| `ClinicalOutcomeUncertaintyProtocol` | Public before submissions | Binds the outcome protocol, cohort, private dependence-manifest fingerprint, confidence level, cluster minima, maximum cluster share, CR1 correction, paired covariance, and stage-by-endpoint strata. |
| `ClinicalOutcomeUncertaintyReport` | Aggregate public after review | Overall and stratum cluster diagnostics, selected cluster-robust intervals, paired Brier-difference intervals, and fixed limitations without assignments or unit labels. |

Real dependence assignments can expose program relationships and remain outside both public
release surfaces. Their fingerprint is public so an evaluator cannot silently replace the
assignment after observing predictions or outcomes.

Real evaluators must use opaque, non-guessable cluster IDs and commitment inputs. Hashing a
predictable program, sponsor, trial, or site identifier without a private high-entropy commitment
does not provide a meaningful privacy boundary.

## Chronology And Binding

The evaluator requires this order:

```text
outcome protocol registration
  <= dependence manifest registration
  <= uncertainty protocol registration
  <= earliest policy submission
  <= outcome prediction deadline
  < outcome window
  <= outcome report freeze
```

All submissions and the base outcome report are fully replayed before uncertainty is computed.
The dependence manifest must exactly cover the cohort's evidence-unit roster.

## Known-Dependence Closure

The manifest cannot split evidence units that are already known to share any of these identities:

- program ID;
- baseline trial ID or source-content SHA-256;
- outcome trial ID or source-content SHA-256.

These links are deduplicated as unordered evidence-unit pairs and reported only as an aggregate
count. The evaluator may merge additional units when a preregistered scientific reason indicates
dependence. Passing the overlap check does not prove independence between different clusters.

## Fixed Strata

Every stratum is determined from the package-bound outcome identity:

```text
stratum = SHA256({stage, endpoint_family})
```

No outcome-dependent regrouping is allowed. Overall and per-stratum diagnostics retain total,
evaluable, and indeterminate unit counts; total and evaluable cluster counts; clusters with no
evaluable outcomes; largest evaluable cluster size/share; and the Kish effective cluster count.

## CR1 Mean Inference

For an additive per-unit quantity `x`, let `N` be the evaluable-unit count, `G` the evaluable
cluster count, and `g(i)` the preregistered cluster for unit `i`:

```text
mean(x) = sum_i x_i / N
U_g = sum_{i: g(i)=g} (x_i - mean(x))
Var_CR1(mean) = [G / (G - 1)] * sum_g U_g^2 / N^2
SE_CR1 = sqrt(Var_CR1)
```

The implementation uses an asymptotic normal critical value and clips intervals to the metric's
natural range. It computes intervals for:

- observed favorable-outcome rate;
- Brier score;
- calibration-in-the-large (`mean(prediction - outcome)`);
- threshold classification accuracy;
- paired policy Brier difference (`B - A`) on the same units and clusters.

The four per-policy quantities are reported overall and within fixed strata. The paired Brier
difference is an overall-board comparison in this v1 contract.

The paired calculation first forms a per-unit loss difference and then aggregates that difference
within cluster. It therefore retains covariance from evaluating both policies on the same board.

Fixed-bin expected calibration error is nonlinear and unstable in sparse bins, so this v1 contract
does not attach a cluster-robust interval to ECE. The point estimate remains in the bound base
outcome report.

## Fail-Closed States

An interval is emitted only when the preregistered cluster-count and maximum-share requirements
are met and the observed cluster standard error is positive at the 12-decimal reporting precision.
Otherwise the point estimate remains and uncertainty fields are `null` with one of these statuses:

- `not_estimable_no_evaluable_units`
- `not_estimable_insufficient_clusters`
- `not_estimable_dominant_cluster`
- `not_estimable_zero_cluster_variance`

When an interval is emitted, its status is `cluster_robust_interval_computed`. This wording is
intentional: computation does not certify asymptotic validity, true cross-cluster independence,
adequate power, or transportability. A real protocol must justify its cluster minimum and share
limit through board-specific simulation or prospective design work.

## CLI

```bash
adds-clinical-evidence evaluate-uncertainty \
  --uncertainty-protocol uncertainty-protocol.json \
  --dependence-manifest evaluator-only-dependence.json \
  --outcome-protocol clinical-outcome-protocol.json \
  --cohort-report clinical-cohort-report.json \
  --submission policy-a-predictions.json \
  --submission policy-b-predictions.json \
  --outcomes evaluator-only-outcomes.json \
  --outcome-report aggregate-clinical-outcome-report.json \
  --output aggregate-cluster-uncertainty-report.json
```

`validate-uncertainty` can perform aggregate-only integrity validation or full private-input
replay. `summarize-uncertainty` emits compact cluster diagnostics and selected policy intervals.
Output writes are atomic and refuse replacement unless `--force` is supplied.

## Machine Contracts

- `rl_env/specs/clinical_outcome_dependence_manifest.schema.json`
- `rl_env/specs/clinical_outcome_uncertainty_protocol.schema.json`
- `rl_env/specs/clinical_outcome_uncertainty_report.schema.json`
- `rl_env/specs/clinical_outcome_uncertainty_summary.schema.json`

The adjacent public example intentionally contains one evidence unit and one cluster. It reproduces
the base point estimates but withholds every interval as `not_estimable_insufficient_clusters`.
The test suite separately exercises positive-variance CR1 and paired calculations over four
synthetic clusters split across two fixed stages. Overall intervals are computed, while each
two-cluster stratum withholds intervals against its three-cluster minimum. That fixture is a
mathematical and no-pooling regression test, not performance evidence.

## Methodological Context

- The [TRIPOD-Cluster explanation and elaboration](https://www.bmj.com/content/380/bmj-2022-071058)
  motivates explicit reporting of cluster construction, heterogeneity, missingness, and validation
  methods in clustered prediction studies.
- Liang and Zeger's [generalized estimating equation framework](https://doi.org/10.1093/biomet/73.1.13)
  established sandwich variance estimation under within-cluster dependence.
- Hong, Lim, and Bae's 2026
  [clustered performance-inference preprint](https://arxiv.org/abs/2606.03656) develops
  cluster-robust intervals and paired comparisons for prediction metrics and reports degraded
  finite-sample coverage in challenging small-cluster settings.

These sources motivate the design but do not validate this repository's synthetic board or select
a universal minimum cluster count.

## Next Research Milestone

The next step is prospective board design rather than another metric: register a multi-program
cohort, define dependence clusters before forecasts, simulate coverage under plausible cluster
sizes and outcome prevalence, and choose stage-by-endpoint sample targets from those simulations.
Only then should the evaluator open a real outcome window and publish aggregate intervals.
