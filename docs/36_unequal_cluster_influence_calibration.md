# Unequal-Cluster Influence Calibration for Pattern-Mixture Intervals

## Research Question

The dependence-closed pattern-mixture layer established that the declared top-level dependence
block is the resampling unit. This study asks a harder question:

> When independent dependence blocks are few, unequal in size, or dominated by one block, which
> interval construction remains calibrated for each fixed binary log-IMOR model functional?

The implementation is in
`agentic_drug_discovery/clinical_outcome_pattern_mixture_influence_calibration.py`. It compares four
methods over the same seeded outcomes and evaluability draws:

1. `delete_one_normal`: the prior full-estimator, delete-one-cluster variance, and normal critical
   value;
2. `delete_one_student_t`: the same point estimate and standard error with a `t_(G-1)` critical
   value;
3. `delete_mj_student_t`: the unequal-group pseudovalue point estimate and variance with a
   `t_(G-1)` critical value; and
4. `delete_mj_webb_multiplier`: an experimental variance-matched one-step Webb six-point
   multiplier interval over delete-`m_j` influence contributions.

No result triggers automatic method selection. The two Student-t methods are operational
candidates. The normal method is a comparator, and the multiplier method is descriptive only.

## Unequal Delete-mj Estimator

Let `theta_hat` be the complete pattern-mixture estimate, `theta_(-j)` the estimate after deleting
independent group `j`, `m_j` its size, `n = sum_j m_j`, `G` the group count, and `h_j = n / m_j`.
The group-size pseudovalue is

```text
p_j = h_j * theta_hat - (h_j - 1) * theta_(-j)
```

The point and variance estimates are

```text
theta_J = sum_j (m_j / n) * p_j
V_J = (1 / G) * sum_j ((p_j - theta_J)^2 / (h_j - 1))
```

When all `m_j` are equal, `V_J` reduces exactly to the ordinary delete-one-group jackknife
variance. The implementation tests this algebraic identity at reporting precision. The point
estimate remains a jackknife bias-corrected estimator and therefore need not equal the original
full-sample estimate even under equal group sizes.

The formulas follow Busing, Meijer, and Van der Leeden,
[Delete-m Jackknife for Unequal m](https://doi.org/10.1023/A:1008800423698). This repository applies
them to independent dependence blocks and the complete nonlinear pattern-mixture functional. It
does not substitute an inverse-variance condition-mean estimator.

## Student-t and Multiplier Intervals

The Student-t methods use an internally evaluated two-sided `t_(G-1)` critical value. Reference
tests include `df=1`, `df=7`, and `df=11`. The Student-t interval must cover every replicate covered
by the corresponding normal interval because its point estimate and standard error are identical
and its critical value is larger.

For the experimental multiplier, define centered influence contributions

```text
c_j = (m_j / n) * (p_j - theta_J)
```

Each multiplier draw uses independent weights from

```text
{-sqrt(3/2), -1, -sqrt(1/2), sqrt(1/2), 1, sqrt(3/2)}
```

and rescales `sum_j w_j c_j` so its raw second moment matches `V_J`. The interval inverts the
precommitted empirical quantiles around `theta_J`. Multiplier RNG uses a scenario-specific,
protocol-seed-specific substream; changing the multiplier seed cannot change outcomes,
evaluability, or any analytic method result.

This is not a regression residual wild-cluster bootstrap. Cluster-jackknife and wild-cluster
methods in the regression literature are important context, especially under few or unequal
clusters, but their regression estimating equations are outside this implementation. See
[MacKinnon, Nielsen, and Webb](https://arxiv.org/abs/2301.04527) and
[MacKinnon and Webb](https://doi.org/10.1111/ectj.12107).

## Production Eligibility

Intervals are calculated in all synthetic scenarios for diagnosis. Operational eligibility is a
separate, immutable gate:

- at least 8 independent analysis clusters; and
- largest cluster fraction no greater than `0.15`.

A method cannot make a production-ineligible design eligible. In particular, passing coverage or
standard-error calibration in a dominant-cluster stress scenario does not override the dominance
gate.

Every method-grid-metric cell also reports canonical counts for full-sample support failure,
leave-one-out support failure, zero resampling variance, invalid multiplier dispersion, and
successful interval construction. No unit, cluster, or replicate records are retained.

## Public Study Design

The public study fixes 500 replicates, a five-point log-IMOR grid `[-2, -1, 0, 1, 2]`, all eight
outcome metrics, 95% intervals, 95% Monte Carlo bounds, and 99 Webb draws. The complete design is
about 91 million bounded work units, below the repository limit of 100 million.

| Scenario | Cluster sizes | G | Largest fraction | Production eligible |
|---|---|---:|---:|---:|
| `balanced-few-8` | `16 x 8` | 8 | 0.1250 | Yes |
| `balanced-reference-12` | `16 x 12` | 12 | 0.0833 | Yes |
| `dominant-cluster-12` | `64, 16 x 11` | 12 | 0.2667 | No |
| `unequal-clusters-12` | `24, 20 x 3, 16 x 3, 12 x 3, 8 x 2` | 12 | 0.1304 | Yes |

Calibration requires:

- Monte Carlo absolute-bias upper bound at most `0.02`;
- interval-yield Wilson lower bound at least `0.95`;
- model-functional coverage Wilson lower bound at least `0.87`; and
- RMS reported-SE to empirical-SD ratio between `0.80` and `1.20`.

## Public Results

The table reports the minimum coverage lower bound and full SE-ratio range over all 40
metric-by-grid cells in each scenario.

| Scenario | Method | Minimum coverage lower | SE-ratio range | All-cell target |
|---|---|---:|---:|---:|
| Balanced few, G=8 | Delete-one normal | 0.872794 | 0.9756-1.0816 | Pass |
|  | Delete-one Student-t | 0.901932 | 0.9756-1.0816 | Pass |
|  | Delete-mj Student-t | 0.906479 | 0.9815-1.0838 | Pass |
|  | Webb multiplier | 0.837679 | 0.9815-1.0838 | Fail |
| Balanced reference, G=12 | Delete-one normal | 0.879461 | 0.9324-1.0486 | Pass |
|  | Delete-one Student-t | 0.904203 | 0.9324-1.0486 | Pass |
|  | Delete-mj Student-t | 0.908761 | 0.9370-1.0580 | Pass |
|  | Webb multiplier | 0.848580 | 0.9370-1.0580 | Fail |
| Dominant cluster, G=12 | Delete-one normal | 0.883924 | 1.0296-1.1294 | Diagnostic only |
|  | Delete-one Student-t | 0.913340 | 1.0296-1.1294 | Diagnostic only |
|  | Delete-mj Student-t | 0.901932 | 0.8845-1.0686 | Diagnostic only |
|  | Webb multiplier | 0.833334 | 0.8845-1.0686 | Fail, diagnostic only |
| Unequal clusters, G=12 | Delete-one normal | 0.895146 | 0.9960-1.1109 | Pass |
|  | Delete-one Student-t | 0.929573 | 0.9960-1.1109 | Pass |
|  | Delete-mj Student-t | 0.927232 | 0.9871-1.0981 | Pass |
|  | Webb multiplier | 0.875013 | 0.9871-1.0981 | Pass, experimental only |

All production-eligible scenarios pass both operational candidate gates. Student-t coverage count
is noninferior to normal in every cell. Equal-size delete-`m_j` standard errors are exactly
equivalent to ordinary delete-one standard errors. The dominant-cluster hard stop is preserved.

The narrow recommendation is:

1. use `t_(G-1)` as the minimum small-cluster upgrade to the existing delete-one interval;
2. report delete-`m_j` as a preregistered unequal-size influence sensitivity, not as an automatic
   replacement for the full estimator;
3. retain the cluster-count and dominance gates independently of simulated calibration passage;
4. keep the one-step Webb multiplier non-operational because its coverage is scenario-dependent
   and misses the target in both balanced designs; and
5. preserve the log-IMOR grid as identification sensitivity rather than combining it with sampling
   uncertainty into one undifferentiated interval.

These results do not establish treatment efficacy, safety, transportability, regulatory
acceptability, or validity of a real dependence manifest.

## Machine Contracts

- `rl_env/specs/clinical_outcome_pattern_mixture_influence_stress_protocol.example.json`
- `rl_env/specs/clinical_outcome_pattern_mixture_influence_pattern_protocol.example.json`
- `rl_env/specs/clinical_outcome_pattern_mixture_influence_pattern_report.example.json`
- `rl_env/specs/clinical_outcome_pattern_mixture_influence_protocol.schema.json`
- `rl_env/specs/clinical_outcome_pattern_mixture_influence_protocol.example.json`
- `rl_env/specs/clinical_outcome_pattern_mixture_influence_report.schema.json`
- `rl_env/specs/clinical_outcome_pattern_mixture_influence_report.example.json`
- `rl_env/specs/clinical_outcome_pattern_mixture_influence_summary.schema.json`
- `rl_env/specs/clinical_outcome_pattern_mixture_influence_summary.example.json`

The protocol fingerprint is
`a57300753f0467f7589aa54c86f94bd7c25448ed37e92abba6c757af61376694`. The report fingerprint is
`80ab9f4ae9dc2c0953bc302151a3846e9dce414a529b7911ad34fe3cd971abc9`.

Rebuild all public artifacts:

```bash
python scripts/audit/build_pattern_mixture_influence_study.py --force
```

## CLI

Run the exact public calibration:

```bash
adds-clinical-evidence calibrate-pattern-mixture-influence \
  --protocol rl_env/specs/clinical_outcome_pattern_mixture_influence_protocol.example.json \
  --pattern-mixture-protocol rl_env/specs/clinical_outcome_pattern_mixture_influence_pattern_protocol.example.json \
  --stress-protocol rl_env/specs/clinical_outcome_pattern_mixture_influence_stress_protocol.example.json \
  --output /tmp/clinical_outcome_pattern_mixture_influence_report.json
```

Validate by complete seeded replay:

```bash
adds-clinical-evidence validate-pattern-mixture-influence \
  --report /tmp/clinical_outcome_pattern_mixture_influence_report.json \
  --protocol rl_env/specs/clinical_outcome_pattern_mixture_influence_protocol.example.json \
  --pattern-mixture-protocol rl_env/specs/clinical_outcome_pattern_mixture_influence_pattern_protocol.example.json \
  --stress-protocol rl_env/specs/clinical_outcome_pattern_mixture_influence_stress_protocol.example.json
```

Emit the compact review surface:

```bash
adds-clinical-evidence summarize-pattern-mixture-influence \
  --report /tmp/clinical_outcome_pattern_mixture_influence_report.json
```

## Next Research Direction

The next empirical layer should challenge the candidate methods rather than add another report
format:

1. vary cluster-size/outcome informativeness so size and influence are correlated;
2. introduce partial dependence-block loss and misspecified block boundaries;
3. add non-nested trial, site, publication, and shared-control dependence dimensions;
4. compare max-cluster deletion diagnostics and influence concentration before interval reporting;
5. evaluate stratum-specific and partially pooled log-IMOR assumptions under the same sampling
   draws; and
6. carry the surviving method set into a locked multi-program endpoint/safety harmonization board
   with provenance-preserving benefit-risk synthesis.
