# Preregistered Clinical Outcome Evaluation

## Scope

This layer turns outcome-free clinical cohort diagnostics into a cutoff-safe evaluation design. It
binds a probabilistic forecast to each exact `ClinicalDecisionPackage` before any registered
outcome source is available, then combines frozen submissions with independently curated endpoint
and safety assessments inside the evaluator boundary.

The prediction target is fixed as:

```text
probability_of_favorable_composite_benefit_risk_outcome
```

This forecast is deliberately separate from the package's `ADVANCE`, `HOLD`, or `DEFER` workflow
decision. `ADVANCE` means that preregistered evidence-workflow criteria were satisfied at the
package cutoff. It is not itself a claim that a future clinical outcome will be favorable.

## Artifact Boundary

| Artifact | Visibility | Contents |
|---|---|---|
| `ClinicalOutcomeEvaluationProtocol` | Public before prediction | Exact cohort report hash, dates, outcome and harmonization commitments, curator-roster commitment, threshold, bins, confidence level, and minimum evaluable units. |
| `ClinicalPredictionSubmission` | Frozen before outcome access; publish only when approved | Policy identity and favorable-outcome probabilities bound to exact package hashes and evidence-unit IDs. |
| `ClinicalOutcomeManifest` | Evaluator only | Unit-level endpoint, safety, and composite labels; post-deadline source provenance; assessment hashes; curator count; and adjudication commitment. |
| `ClinicalOutcomeEvaluationReport` | Aggregate public after review | Attrition, Wilson intervals, Brier and calibration metrics, threshold metrics, paired policy comparisons, overlap counts, and required limitations. |

Real outcome manifests, per-unit submissions, curator material, and unit-level evaluation rows are
excluded from the public repository and Hugging Face release. The checked-in examples are synthetic
contract fixtures.

## Temporal Contract

```mermaid
flowchart LR
    C["Outcome-free cohort report"] --> P["Protocol registration"]
    P --> S["Package-bound submissions"]
    S --> D["Prediction deadline"]
    D --> W["Outcome window"]
    W --> A["Blinded endpoint and safety assessment"]
    A --> F["Outcome manifest freeze"]
    F --> R["Aggregate report"]
```

The implementation requires:

1. every cohort package cutoff to be on or before protocol registration;
2. every submission to fall between registration and the prediction deadline;
3. every registered outcome source to become available on or after the preregistered outcome-window start, which is strictly after the deadline;
4. every assessment to occur no earlier than the end of the outcome window;
5. every source to be available no later than the assessment it supports;
6. every source and assessment to predate or equal the manifest freeze;
7. exact protocol, cohort-report, package, policy, evidence-unit, roster, and manifest hash binding.

An outcome source whose content hash appeared in the baseline cohort fails closed. A later record
from the same trial may retain the same trial ID, because later trial results can be the intended
outcome. The content hash must still be novel and post-deadline. Cross-unit source-hash and trial-ID
reuse is counted in the aggregate report so dependence remains visible.

## Endpoint And Safety Outcome Rule

Independent reviewers assign separate statuses to the registered endpoint and safety domains:

- `favorable`
- `unfavorable`
- `indeterminate`

The composite rule is conservative and executable:

```text
if endpoint is unfavorable or safety is unfavorable:
    composite = unfavorable
else if endpoint is favorable and safety is favorable:
    composite = favorable
else:
    composite = indeterminate
```

Every assessment requires provenance covering both endpoint and safety, hashes for each domain's
assessment, an adjudication hash, the preregistered minimum number of independent curators, and
true policy-blinding, conflict-free, and adjudicator-independence declarations. These commitments
make omissions and rebinding detectable; they do not prove the underlying attestations truthful.

## Evaluation Unit

The denominator is the exact cohort `evidence_unit_id`, not the package count. Multiple policies
can forecast one evidence unit, but that unit contributes once to each policy's metrics and only to
paired comparisons between policies. This prevents policy variants over one synthesis from being
misrepresented as independent clinical outcomes.

The outcome manifest must cover every evidence unit. Units that cannot be adjudicated are labeled
`indeterminate`, retained in attrition counts, and excluded from binary performance denominators.
They are never silently dropped or converted to an unfavorable label.

## Metrics

For each policy submission, the aggregate report includes:

- total, evaluable, and indeterminate unit counts plus the preregistered minimum flag;
- observed and predicted favorable rates with exact counts and Wilson intervals;
- confusion counts, accuracy, sensitivity, specificity, positive predictive value, and negative
  predictive value at the preregistered threshold;
- mean favorable probability, Brier score, calibration-in-the-large, and fixed-bin expected
  calibration error;
- every preregistered calibration bin, including empty bins with `null` estimates.

Submissions must exactly cover the cohort, so one pairwise row is required for every policy pair
over the same evidence-unit roster. Rows report shared and evaluable counts, each policy's mean
Brier score on exactly the same outcomes, `B - A` paired Brier difference, lower/equal-score counts,
and threshold-classification disagreements. They do not rank or select a policy.

Wilson intervals describe finite evaluable-unit uncertainty only. They do not account for
cross-unit clustering, shared trial infrastructure, adjudication uncertainty, or repeated policy
evaluation. A real analysis should prespecify cluster-aware or hierarchical uncertainty once the
board's dependence structure and sample size support it.

## CLI

The shipped synthetic artifacts reproduce the aggregate report:

```bash
adds-clinical-evidence evaluate-outcomes \
  --protocol rl_env/specs/clinical_outcome_evaluation_protocol.example.json \
  --cohort-report rl_env/specs/clinical_evidence_cohort_report.example.json \
  --submission rl_env/specs/clinical_prediction_submission.example.json \
  --submission rl_env/specs/clinical_prediction_submission.relaxed.example.json \
  --outcomes rl_env/specs/clinical_outcome_manifest.example.json \
  --output synthetic-clinical-outcome-report.json

adds-clinical-evidence validate-outcomes \
  --report synthetic-clinical-outcome-report.json \
  --protocol rl_env/specs/clinical_outcome_evaluation_protocol.example.json \
  --cohort-report rl_env/specs/clinical_evidence_cohort_report.example.json \
  --submission rl_env/specs/clinical_prediction_submission.example.json \
  --submission rl_env/specs/clinical_prediction_submission.relaxed.example.json \
  --outcomes rl_env/specs/clinical_outcome_manifest.example.json

adds-clinical-evidence summarize-outcomes \
  --report synthetic-clinical-outcome-report.json
```

`validate-outcomes` can also validate report integrity and internal metric consistency without
private inputs. Full replay requires the protocol, cohort report, every submission, and the outcome
manifest together. Output writes are atomic and refuse replacement unless `--force` is supplied.

## Machine Contracts

- `rl_env/specs/clinical_outcome_evaluation_protocol.schema.json`
- `rl_env/specs/clinical_prediction_submission.schema.json`
- `rl_env/specs/clinical_outcome_manifest.schema.json`
- `rl_env/specs/clinical_outcome_evaluation_report.schema.json`
- `rl_env/specs/clinical_outcome_evaluation_summary.schema.json`

Strict readers reject duplicate keys, non-finite values, unknown fields, unsupported versions,
noncanonical ordering, impossible composites, metric inconsistency, and integrity drift.

## Synthetic Result Boundary

The example contains one synthetic evidence unit, one favorable synthetic outcome, and two policy
forecasts. Its Brier and calibration values demonstrate deterministic computation only. A one-unit
fixture cannot establish calibration, discrimination, clinical utility, or policy superiority,
even though its development protocol sets a minimum of one so every code path is executable.

`docs/31_cluster_robust_clinical_outcome_uncertainty.md` implements the dependence-aware analysis
contract: preregistered evaluator-only cluster assignments, known-overlap closure, stage-by-endpoint
diagnostics, CR1 intervals for additive metrics, and paired Brier covariance. Its public example
fails closed because one cluster cannot support an interval. The real milestone remains a
prospectively designed multi-program board; real outcome/dependence manifests and unit scores stay
under independent evaluator control.
