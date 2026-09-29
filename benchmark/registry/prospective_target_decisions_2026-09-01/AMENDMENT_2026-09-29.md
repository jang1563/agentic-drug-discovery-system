# Amendment 1 (2026-09-29): how answers and confidences become AUROC scores

Applies to the prospective target-decision registry (cutoff 2026-09-01; combined SHA-256
`005413f80162a857fd8452e244e0e1ad2d3ba6035ca38fc222260d05a7e73b4d`) and the prospective CTDBench trial registry
(cutoff 2026-09-28; combined SHA-256 `3fef2dd85011751589f3a34db980a9d35ba97e6d0147b1840482cbf2ce54d3fc`). It was
recorded before any outcome of either registry exists. The first reads are 2028-06-01 for the trials and 2028-12-01
for the targets.

## Problem

The pre-registrations score "AUROC of stated confidence" but do not fix how an answer and its confidence become a
score. The frozen code snapshots use P(advance) = confidence for an `advance` answer and 1 − confidence for a `stop`
answer.

Some models state a confidence below 0.5 for their own forced answer:

- gpt-oss-120b in 72–89% of its no-evidence answers and 12–16% of its full-packet answers.
- Claude Haiku 4.5, Qwen3.8-27B and Gemini 2.5 Pro in up to 14%.

Under the snapshot mapping such an answer lands on the wrong side, which inverts part of the ranking. In a
retrospective target panel this moved gpt-oss-120b's no-evidence AUROC from 0.865 to 0.544.

## Scoring from this amendment on

- **AUROC (primary wherever the pre-registration names AUROC).** Score = 0.5 + confidence/2 for `advance`, 0.5 − confidence/2 for `stop`, and 0.5 for any other answer. The decision sets the side and the confidence sets the order within it. For a model whose confidences are all at least 0.5 this ranking is identical to the snapshot's.
- **AUROC with the snapshot mapping** is reported next to it.
- **Brier score** keeps the stated mapping: confidence is the probability that the answer is right. The number of answers with confidence below 0.5 is reported for each model.
- **Nothing else changes.** Cohorts, labels, rules, predictions, read dates and every other metric stay as registered.

## Basis

The change was decided on retrospective panels only: CTDBench v2, the recent-completion cohort and the target-level
panels. The registries' own predictions were examined only for the share of confidences below 0.5, which needs no
outcome.
