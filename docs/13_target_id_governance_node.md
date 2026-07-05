# Target-ID Decision Node — Upstream Extension (results card)

Date: 2026-07-05
Status: single evaluation set, small-N, honest scope

## Purpose

An upstream **target-identification** decision node for the same auditable
decision environment described in `docs/12_scd_vertical_slice.md`. Given a
`(disease, target)` pair, the node emits exactly one action from
**advance / stop / defer / request_more_evidence / flag**, with abstention
first-class and calibration attached, using **public data only**. It extends the
retrospective + prospective decision framing one stage upstream (target selection),
before the clinical and regulatory stages.

## Read the scope honestly first

- Evaluated on **one set of 32 `(disease, target)` pairs** (16 credible-target,
  16 non-credible) across 22 diseases — **small N**. This is not a validated
  target predictor.
- The cross-stage clinical signal (a target's prior clinical track record) is
  **label-adjacent by construction**, so the cross-stage results demonstrate
  **cross-stage integration and calibration recovery, not out-of-distribution
  prediction**.
- **Time-gating** excludes pre-registry-era approved drugs (public trial
  registration began around 2000); those targets fall back to genetic evidence only.
- Distribution-free calibration (RCPS) is certifiable only at **loose risk levels**
  at this sample size.
- Every output is **decision support with an auditable evidence trail** — never a
  claim of a validated target.

## What the node is

Evidence available at the node:

1. **Human genetic / functional association** from the Open Targets Platform,
   with the **drug-derived datatypes masked out**. Masking prevents the answer
   leaking through "a drug already exists for this target" and forces the decision
   to rest on independent genetic/functional evidence.
2. A **time-gated clinical track record** from ClinicalTrials.gov: the highest
   clinical phase reached for the disease as of a decision-time gate, plus verbatim
   trial-termination reasons (so the agent can weigh an efficacy failure against a
   business/enrollment stop).

The action space and the multi-stage flow are shared with
`chains/discovery_flow.py`. Abstention (`defer` / `request_more_evidence`) is a
first-class action, not a fallback.

## Evaluation set (public identifiers)

32 pairs, balanced 16 credible / 16 non-credible, spanning 22 diseases. Each pair
uses public gene symbols, disease ontology identifiers, and public trial/approval
outcomes; pairs were curated and adversarially cross-checked against public
sources. Per-record gold labels are not shipped (see the release boundary).

- Illustrative credible targets: `HBB` / sickle cell disease; `JAK2` / primary
  myelofibrosis; `CFTR` / cystic fibrosis; `EGFR` / non-small-cell lung cancer.
- Illustrative non-credible targets (well-documented late-stage failures):
  `BACE1` / Alzheimer disease; `CETP` / coronary artery disease; `IGF1R` /
  non-small-cell lung cancer.

## Results (single evaluation set)

**Construct validity.** A no-reasoning structural threshold on the masked evidence
and an always-advance baseline both stay near chance; a reasoning agent clears
them. A diagnostic control that is allowed to see the masked drug-derived evidence
scores near-perfectly — confirming that the masking removes a real circularity
rather than genuine signal.

| Policy (masked genetic evidence) | Selective accuracy |
| --- | --- |
| Reasoning agent | ~0.82 (stable across seeds, ~0.81–0.92) |
| No-reasoning threshold | ~0.62 |
| Always-advance | 0.50 |

**Cross-stage.** Adding the time-gated clinical track record raises selective
accuracy and corrects the "strong-genetics-but-clinically-failed" class (for
example `BACE1`, `CETP`, `IGF1R`), while the agent abstains where the clinical
record is thin. The lift holds across three model families (each roughly +0.11 to
+0.19 selective accuracy), so the gain is driven by **evidence coverage, not model
choice**.

**Calibration.** A leave-one-out isotonic + RCPS conformal-risk procedure over a
risk model (multi-sample disagreement plus a clinical-track-record cross-check)
predicts the genetics-only over-advances (AUROC ~0.94), enabling selective
abstention on the highest-risk calls. Distribution-free RCPS certifies the accept
set only at loose risk levels at this sample size.

**End-to-end.** In a retrospective eight-asset sickle-cell trajectory, the node
plus the clinical and regulatory stages reach the correct terminal decision while
both trivial baselines fail; the upgraded node raises early caution one to two
stages before the clinical failure for assets whose targets carry a failure track
record, and stays quiet for targets with a clean record. A prospective
decision-support demo on an ongoing asset returns a calibrated **watch / defer**
with the load-bearing uncertainty stated explicitly and no early red flag.

## Data sources

Open Targets Platform, ClinicalTrials.gov, openFDA, and EMA — all public. No
private or restricted data is used.

## Not included (release boundary)

Raw experiment scripts, per-record gold labels, run logs, and local paths are not
part of the public surface, consistent with `docs/release_boundary.md`.

## License

Apache-2.0.
