# Informative Cluster Size, Estimand Drift, and Influence Concentration

## Research Question

The prior calibration established a Student-t minimum for few independent dependence blocks and
kept delete-`m_j` as an unequal-size sensitivity. It did not answer what quantity should be
estimated when cluster size is associated with outcome risk.

This study asks two separate questions:

1. How far can unit-weighted and cluster-balanced pattern-mixture functionals diverge when cluster
   size is informative?
2. How do the same size-outcome profiles change resampling calibration and concentration of
   influence?

The implementation is
`agentic_drug_discovery/clinical_outcome_informative_cluster_size.py`. It binds an exact stress
protocol to block-specific favorable-prevalence profiles, computes both known truths at every
fixed log-IMOR, and retains aggregate results only.

Informative cluster size is established methodological territory rather than a novelty claim.
Within-cluster resampling was developed for settings where outcome risk is related to cluster size
([Hoffman, Sen, and Weinberg, 2001](https://doi.org/10.1093/biomet/88.4.1121)), and inverse
cluster-size weighted marginal estimating equations explicitly target cluster-balanced summaries
([Williamson, Datta, and Satten, 2003](https://pubmed.ncbi.nlm.nih.gov/12762439/)). The contribution
here is to make that estimand distinction explicit inside the project's provenance-bound
pattern-mixture and benefit-risk evaluation path.

## Two Functionals

For independent analysis block `j`, let `m_j` be enrolled units and `theta_j(delta)` the block's
pattern-mixture functional at fixed log-IMOR `delta`. The two targets are

```text
theta_U(delta) = sum_j m_j * theta_j(delta) / sum_j m_j
theta_C(delta) = sum_j theta_j(delta) / G
```

`theta_U` describes the average enrolled unit in the finite design. `theta_C` describes the
average analysis block. They coincide under equal block sizes or when block functionals do not
vary with size. Otherwise, choosing weights chooses an estimand.

The study compares three intervals:

1. `unit_weighted_delete_one_student_t`: `m_j`-weighted block-functional estimate,
   delete-one-block variance, and `t_(G-1)` critical value;
2. `unit_weighted_delete_mj_student_t`: unequal-size pseudovalue estimate and variance with the
   same Student-t critical value; and
3. `cluster_balanced_delete_one_student_t`: equal average of block-specific pattern-mixture
   estimates with delete-one-block Student-t inference.

The first two target `theta_U`; the third targets `theta_C`. Delete-`m_j` changes the jackknife
calculation but does not turn a unit-weighted estimator into a cluster-balanced estimator. All
three methods evaluate the same block-specific pattern-mixture functional before aggregation.
This prevents a global aggregation shortcut from introducing a second, nonlinear functional into
what is intended to be a weighting-only comparison.

## Fixed-Profile Inference

Block sizes and block-specific prevalence profiles remain fixed across all 500 replicates. Each
replicate redraws correlated binary outcomes and outcome-dependent evaluability conditional on
those indexed block distributions, including beta-binomial outcome variation. It does not redraw
block sizes or the deterministic size-linked mean-prevalence profile. Therefore empirical SD and
interval coverage target repeated outcome sampling for a finite, fixed cluster configuration.

This distinction matters. A delete-one jackknife treats persistent block-to-block heterogeneity as
part of between-block uncertainty, while the conditional Monte Carlo design does not redraw the
specified size-linked mean heterogeneity. An SE ratio above one is evidence of overconservatism for
this conditional target; it is not evidence that the same interval would be too wide for a
superpopulation that samples new cluster sizes and mean prevalences.

## Public Design

The public study uses one prediction stratum to isolate informative size from sparse within-block
support, 12 independent blocks, ICC `0.05`, favorable/unfavorable evaluability probabilities
`0.90/0.55`, all eight outcome metrics, and five log-IMOR values. The reference value
`-1.996553881874` is the exact outcome-generating selection shift at reporting precision.

| Scenario | Block sizes | Cluster truth | Unit truth | Direction at 0.5 | Eligible |
|---|---|---:|---:|---|---:|
| `balanced-null-12` | `128 x 12` | 0.5000 | 0.5000 | Same | Yes |
| `unequal-null-12` | `192, 160 x 3, 128 x 3, 96 x 3, 64 x 2` | 0.5000 | 0.5000 | Same | Yes |
| `unequal-informative-benefit-12` | Same unequal design | 0.4800 | 0.5261 | Opposite | Yes |
| `unequal-informative-harm-12` | Same unequal design | 0.5200 | 0.4739 | Opposite | Yes |
| `dominant-informative-benefit-12` | `512, 128 x 11` | 0.4750 | 0.5300 | Opposite | No |

Production eligibility remains independent of results: at least eight blocks and maximum enrolled
unit share `0.15`. The dominant scenario has share `0.2667` and cannot become operational through
good bias or coverage.

Calibration requires a Monte Carlo absolute-bias upper bound at most `0.02`, interval-yield Wilson
lower bound at least `0.95`, coverage Wilson lower bound at least `0.87`, and RMS reported-SE to
empirical-SD point ratio between `0.70` and `1.30`. The ratio does not carry its own Monte Carlo
confidence interval in this study.

## Public Results

The table reports the reference observed-favorable-rate cell. Bias is relative to each method's
declared target.

| Scenario | Method | Target bias | Alternate bias | Coverage | SE / empirical SD |
|---|---|---:|---:|---:|---:|
| Balanced null | Unit-weighted delete-one | -0.00034 | -0.00034 | 0.944 | 1.005 |
|  | Unit-weighted delete-`m_j` | -0.00034 | -0.00034 | 0.944 | 1.005 |
|  | Cluster-balanced | -0.00034 | -0.00034 | 0.944 | 1.005 |
| Unequal null | Unit-weighted delete-one | 0.00097 | 0.00097 | 0.958 | 1.049 |
|  | Unit-weighted delete-`m_j` | 0.00097 | 0.00097 | 0.950 | 1.003 |
|  | Cluster-balanced | 0.00178 | 0.00178 | 0.948 | 0.996 |
| Informative benefit | Unit-weighted delete-one | -0.00081 | 0.04527 | 0.986 | 1.526 |
|  | Unit-weighted delete-`m_j` | -0.00081 | 0.04527 | 0.986 | 1.465 |
|  | Cluster-balanced | -0.00064 | -0.04673 | 0.994 | 1.586 |
| Informative harm | Unit-weighted delete-one | 0.00102 | -0.04507 | 0.994 | 1.477 |
|  | Unit-weighted delete-`m_j` | 0.00102 | -0.04507 | 0.994 | 1.428 |
|  | Cluster-balanced | 0.00162 | 0.04771 | 0.996 | 1.534 |
| Dominant benefit | Unit-weighted delete-one | -0.00039 | 0.05461 | 0.982 | 2.316 |
|  | Unit-weighted delete-`m_j` | -0.00039 | 0.05461 | 0.976 | 1.455 |
|  | Cluster-balanced | 0.00021 | -0.05479 | 0.982 | 1.238 |

The estimators remain close to their own known truths. In the informative eligible scenarios,
absolute own-target bias is at most `0.00163`, while evaluating against the other estimand creates
absolute differences of `0.04507-0.04771`. Both informative profiles reverse direction at the
precommitted `0.5` threshold. An interval method cannot resolve that scientific choice.

Across all `600` method-by-metric-by-grid cells, every bias, interval-yield, and coverage target
passes; maximum observed absolute target bias is `0.00795`. The `320` failed cells fail only the
SE-calibration criterion. All three methods pass every target in both null scenarios, while none
passes all cells in either eligible informative scenario. Reference coverage rises to
`0.986-0.996` and SE ratios rise to `1.428-1.586`; the failure is overconservative uncertainty
under the fixed-profile sampling frame, not material own-target bias or low interval yield.

Influence diagnostics reinforce the distinction:

Delete-one methods define influence as the leave-one-block estimate minus the full estimate.
Delete-`m_j` instead reports each block's weighted pseudovalue contribution. The normalized shares
measure concentration within a method; their absolute magnitudes are not a common influence scale.

| Scenario | Method | Mean max influence share | Largest block is most influential | Largest deletion flips direction |
|---|---|---:|---:|---:|
| Informative benefit | Unit-weighted delete-one | 0.230 | 0.713 | 0.323 |
|  | Unit-weighted delete-`m_j` | 0.222 | 0.691 | Not applicable |
|  | Cluster-balanced | 0.190 | 0.359 | 0.190 |
| Informative harm | Unit-weighted delete-one | 0.223 | 0.652 | 0.309 |
|  | Unit-weighted delete-`m_j` | 0.216 | 0.632 | Not applicable |
|  | Cluster-balanced | 0.186 | 0.325 | 0.171 |
| Dominant benefit | Unit-weighted delete-one | 0.452 | 0.974 | 0.684 |
|  | Unit-weighted delete-`m_j` | 0.396 | 0.962 | Not applicable |
|  | Cluster-balanced | 0.228 | 0.674 | 0.142 |

Delete-`m_j` modestly reduces unit-weighted influence concentration but preserves the unit-weighted
target and its cross-estimand difference. Cluster balancing reduces size-driven concentration,
but that is a consequence of its different scientific target, not a free robustness correction.

## Decision Rule

The operational design should preregister:

1. whether the primary benefit-risk question concerns enrolled units or equal-weight clinical
   units such as trials or sites;
2. the analysis block that carries independent information;
3. a secondary estimate for the alternate weighting when informative size is plausible;
4. cluster dominance and influence diagnostics that cannot be overridden by interval passage; and
5. whether uncertainty is conditional on the observed blocks or intended for a cluster
   superpopulation.

The software reports both truths in synthetic calibration but performs no automatic estimand
selection in operational use.

## Machine Contracts

- `rl_env/specs/clinical_outcome_informative_cluster_size_stress_protocol.example.json`
- `rl_env/specs/clinical_outcome_informative_cluster_size_protocol.schema.json`
- `rl_env/specs/clinical_outcome_informative_cluster_size_protocol.example.json`
- `rl_env/specs/clinical_outcome_informative_cluster_size_report.schema.json`
- `rl_env/specs/clinical_outcome_informative_cluster_size_report.example.json`
- `rl_env/specs/clinical_outcome_informative_cluster_size_summary.schema.json`
- `rl_env/specs/clinical_outcome_informative_cluster_size_summary.example.json`

The protocol fingerprint is
`23918d52ed465928701ddd70ca40f5a7dc139a75afe84bafca691529997d0317`. The report fingerprint is
`1b0d6a6d8b4bead1b5ad06df5b83dac1296f1be39d072feb6de25bdd7aab8eda`.

Rebuild all public artifacts:

```bash
python scripts/audit/build_informative_cluster_size_study.py --force
```

Run and replay through the CLI:

```bash
adds-clinical-evidence analyze-informative-cluster-size \
  --protocol rl_env/specs/clinical_outcome_informative_cluster_size_protocol.example.json \
  --stress-protocol rl_env/specs/clinical_outcome_informative_cluster_size_stress_protocol.example.json \
  --output /tmp/clinical_outcome_informative_cluster_size_report.json

adds-clinical-evidence validate-informative-cluster-size \
  --report /tmp/clinical_outcome_informative_cluster_size_report.json \
  --protocol rl_env/specs/clinical_outcome_informative_cluster_size_protocol.example.json \
  --stress-protocol rl_env/specs/clinical_outcome_informative_cluster_size_stress_protocol.example.json

adds-clinical-evidence summarize-informative-cluster-size \
  --report /tmp/clinical_outcome_informative_cluster_size_report.json
```

## Next Research Direction

The next experiment should separate the newly exposed sampling frameworks:

1. retain the current fixed-profile conditional study as one target;
2. add a hierarchical superpopulation study that redraws cluster prevalences while preserving a
   precommitted size-outcome association;
3. compare conditional and superpopulation coverage for the same three estimators;
4. evaluate partially pooled block functionals without allowing shrinkage to choose the estimand;
5. then introduce dependence-block loss and non-nested trial, site, publication, and shared-control
   dependence; and
6. carry the surviving estimand and uncertainty contracts into the multi-program endpoint/safety
   harmonization board.
