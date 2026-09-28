# Prospective target-decision registry: pre-registration (registered 2026-09-28)

## Why prospective

Retrospective target-level decisions are answered by recall. On 164 stage-matched items, Claude Opus 5.5 reached
balanced accuracy 0.988 from the target name and disease alone and, asked directly, knew the approval outcome of all
164 pairs (97.6% agreement with the event gold); even two-year phase 3 starts were known for 89% of 116 programs.
Identity masking did not remove this (0.957 and 0.879). Only outcomes that have not happened yet can test whether a
model reads the evidence. This registry fixes the cohort, the inputs, the questions, the resolution rules and the
scoring before any outcome is known.

## Cohort (frozen at registration)

- Registration cutoff: **2026-09-01**. Source data: Open Targets Platform clinical layer (release files dated
  2026-09-07), ClinicalTrials.gov records fetched at registration, PubMed, Drugs@FDA.
- Unit: a (target, disease) program. Included when the target is **novel** (no target-selective drug marketed
  before the cutoff), an **investigational** target-selective drug has an on-target phase 2 in the disease that
  **started in the four years before the cutoff**, and there is **no on-target phase 3 (or 2/3, 4)** in the disease or
  a subtype and **no approval** for them. Near-duplicate programs are collapsed per (target, investigational drugs,
  therapeutic area).
- Files: `prospective_cohort_2026-09-01.jsonl`, `packets_target_prospective_2026-09-01.jsonl` and its masked
  variant. Target-selective = at most two genes over all mechanism rows, after removing ADC payload and toxin
  targets (`build_target_universe.py`).

## Questions and predictions

Each model receives the cutoff-safe packet (genetics published before the cutoff, on-target trials with their status
as of the cutoff, PubMed before the cutoff) and answers two forced-choice questions with a confidence:

1. **Progression (primary, two years):** will a drug acting on this target start a phase 3 (or phase 2/3) trial in
   this disease between 2026-09-01 and 2028-09-01?
2. **Approval (secondary, ten years):** will a drug acting on this target be approved (FDA label, EMA or PMDA) for
   this disease or a subtype by 2036-09-01?

A no-evidence prediction (target and disease only) is recorded for each question as a prior-belief reference.
Models, settings and prompts are those in `run_target_eval.py`, pinned by its SHA-256 in the manifest; predictions
are stored per question and model in `prospective_predictions/`. The count-feature logistic baselines, fitted on the
retrospective stage-matched sets, are frozen as `prospective_predictions/count_baselines.json` with their predictions.

## Resolution (fixed now)

- Progression resolves on **2028-09-01** from ClinicalTrials.gov and the Open Targets clinical layer of that date:
  `advance` if an on-target phase 3 or phase 2/3 trial in the disease or a subtype has a start date in
  [2026-09-01, 2028-09-01) and is not withdrawn; otherwise `stop`. Trials registered late but started inside the
  window count; a 90-day grace period for registration lag applies (final read no earlier than 2028-12-01).
- Approval resolves on **2036-09-01** with the approval rules of `build_target_universe.py` (a target-selective
  drug approved by a regulator for the disease or a subtype); interim reads are descriptive only.
- Programs whose target or disease mapping is found to be wrong at resolution are dropped with a recorded reason,
  never relabelled by outcome.

## Scoring (fixed now)

Balanced accuracy and AUROC of stated confidence per model and question, with bootstrap 95% CIs over programs;
Brier score and a reliability curve; comparison with the count-feature logistic model fitted on the retrospective
stage-matched sets and applied unchanged; the gain of full over no-evidence predictions. The expected progression
base rate is low (about 3–7% of live programs started phase 3 within two years at the 2019–2023 cutoffs), so the
primary metric is AUROC with the Brier score, and balanced accuracy is secondary.

## Integrity

`registry/2026-09-01/MANIFEST.json` records SHA-256 hashes of every file in the frozen registry folder (cohort,
packets, predictions, count baselines, a code snapshot and this file) and one combined hash. The combined hash is the commitment: publishing it (or the manifest) before resolution makes the
registry verifiable without revealing predictions early.
