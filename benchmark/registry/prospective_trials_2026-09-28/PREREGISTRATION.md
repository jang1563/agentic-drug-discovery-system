# Prospective CTDBench trial registry: pre-registration (registered 2026-09-28)

## Why prospective

Retrospective decide-at-cutoff scores for frontier models are partly memory. In the CTDBench v2 static panel
(266 trials), Claude Opus 5.5 scored the same balanced accuracy from the trial id and title alone as from the full
cutoff-safe packet (0.680 vs 0.689), and in the agentic panel Gemini 3.8 Flash stated the actual post-cutoff outcome
of the trial under decision in 10.5% of episodes. At the target level the effect is extreme (Opus 5.5 0.988 with no
evidence). Trials that have not read out cannot be remembered. This registry fixes the cohort, the inputs, the
question, the resolution rules and the scoring before any outcome exists.

## Cohort (frozen at registration)

- ClinicalTrials.gov query run on 2026-09-28: interventional, phase 2 / 2-3 / 3, at least one drug or biological
  intervention, overall status ACTIVE_NOT_RECRUITING (enrollment finished), primary completion date between
  2026-10-01 and 2027-03-31, at least one primary outcome, no posted results. 1,179 trials were eligible.
- Sample: 400 trials, stratified by phase group (phase 3 if any phase 3 component, else phase 2) and sponsor class
  (industry vs other), proportional to the eligible counts, seed 20260928 (`fetch_cohort.py`, `cohort.json`).
- Each trial's full registry record at registration is kept in `ctgov/`.

## Inputs

One packet per trial (`build_prospective_trials.py`, `packets_prospective.jsonl`), in the CTDBench v2 step-3 layout
with a single cutoff, the registration date 2026-09-28: the results-free protocol; prior trials of the same drugs
that started before the cutoff (searched newest first), with compact posted-result summaries only for results
posted before the cutoff; PubMed records published before the cutoff; Drugs@FDA status at the cutoff.

## Question and predictions

"Decide what the sponsor should do with this program in this indication once the trial reads out": forced choice
advance / stop with a confidence (`run_prospective_trials.py`). Seven models (Claude Opus 5.5 at effort low, Claude
Sonnet 5, Claude Haiku 4.5, Gemini 3.8 Flash, Gemini 2.5 Pro at reasoning effort low, gpt-oss-120b, Qwen3.8-27B),
each with the full packet and with no evidence (trial id and title only) as a prior-belief reference.

## Resolution (fixed now)

Gold is the CTDBench v2 event-anchored label, computed by `events.compose` (the version in the code snapshot) from
ClinicalTrials.gov records and Drugs@FDA fetched at each read, with the v2 rules unchanged: posted primary
significance and direction (E1), two-arm separation (E2), termination class (E3), a later higher-phase trial of an
investigational drug in the same condition (E4), no progression within four years (E4−), first approval after the
trial with an indication match (E5), endpoint-keyword direction (E6); conflicts resolve to verify.

- **Interim read on 2028-06-01**: labels from posted results, terminations, progression and approvals available by
  then. Reported as interim.
- **Final read on 2031-06-01**: the full v2 rule set, including four-year non-progression.
- Trials whose primary completion slips stay in the cohort and are resolved from their actual dates. A trial found
  to be out of the v2 scope at resolution (for example not a drug trial) is dropped with a recorded reason, never
  relabelled by outcome.

## Scoring (fixed now)

Balanced accuracy on decisive gold (advance / stop) at each read with bootstrap 95% CIs over trials, with coverage
by label tier reported; AUROC of stated confidence; Brier score; the difference between full-packet and
no-evidence predictions per model; and, as a descriptive reference, each model's retrospective CTDBench v2 score.

## Integrity

`registry/2026-09-28/MANIFEST.json` records the SHA-256 of every file in the frozen registry folder (cohort, registry
records, packets, predictions, a code snapshot and this file) and one combined hash. The combined hash is published
before any outcome is known; the predictions stay private until resolution.
