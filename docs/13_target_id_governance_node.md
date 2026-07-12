# Target-ID Decision Node — Upstream Extension (results card)

Date: 2026-07-05
Status: single evaluation set, small-N, honest scope

## Purpose

An upstream **target-identification** decision node for the same auditable
decision environment described in `docs/12_scd_vertical_slice.md`. Given a
`(disease, target)` pair, the node emits exactly one action from
**advance / stop / defer / request_more_evidence / flag**, with abstention
first-class and retrospective calibration analysis attached, using **public data
only**. It extends the
retrospective + prospective decision framing one stage upstream (target selection),
before the clinical and regulatory stages.

## Read the scope honestly first

- Evaluated on **one set of 32 `(disease, target)` pairs** (16 credible-target,
  16 non-credible) across 23 diseases — **small N**. This is not a validated
  target predictor.
- The cross-stage clinical signal (a target's prior clinical track record) is
  **label-adjacent by construction**, so the cross-stage results demonstrate
  **cross-stage integration and retrospective risk analysis, not
  out-of-distribution prediction**.
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

32 pairs, balanced 16 credible / 16 non-credible, spanning 23 diseases. Each pair
uses public gene symbols, disease ontology identifiers, and public trial/approval
outcomes; pairs were curated and adversarially cross-checked against public
sources. Per-record gold labels are not shipped (see the release boundary).

- Illustrative credible targets: `HBB` / sickle cell disease; `JAK2` / primary
  myelofibrosis; `CFTR` / cystic fibrosis; `EGFR` / non-small-cell lung cancer.
- Illustrative non-credible targets (well-documented late-stage failures):
  `BACE1` / Alzheimer disease; `CETP` / coronary artery disease; `IGF1R` /
  non-small-cell lung cancer.

## Results (single evaluation set)

**Scoped construct-validity control.** On the same 32 pairs, five repeated calls
of the masked Sonnet policy yielded pooled selective accuracy 0.842 at 0.713
coverage (overall accuracy 0.600), with per-repeat selective accuracy 0.810–0.917.
A no-reasoning masked threshold reached 0.625 selective accuracy at 0.750
coverage (overall 0.469), and always-advance reached 0.500. A diagnostic threshold
allowed to see the drug-derived field reached 0.781 overall. That diagnostic
difference is evidence of a leakage signal and does not establish external
validity.

| Policy | Selective accuracy | Coverage | Overall accuracy |
| --- | ---: | ---: | ---: |
| Masked Sonnet, pooled over five repeated calls | 0.842 | 0.713 | 0.600 |
| No-reasoning masked threshold | 0.625 | 0.750 | 0.469 |
| Always-advance | 0.500 | 1.000 | 0.500 |
| Drug-field-visible diagnostic threshold | 0.781 | 1.000 | 0.781 |

**Cross-stage.** Adding the time-gated clinical track record improved selective
accuracy on this same constructed set for three model families, while coverage
also changed: Claude 0.826/0.719 → 0.942/0.812 (+0.116 selective accuracy),
GPT-4o 0.833/0.750 → 0.968/0.984 (+0.135), and DeepSeek 0.754/0.953 →
0.935/0.969 (+0.181), where each pair is selective accuracy/coverage. Because
the clinical signal is label-adjacent and the accept sets differ, this supports
cross-stage integration on this set, not a causal model-independence claim or
out-of-distribution prediction.

**Calibration.** A leave-one-out isotonic + RCPS procedure used retrospective
target gold. For genetics-only calls, n=23 committed decisions yielded AUROC
0.939 against error, but **no RCPS certificate**. For the cross-stage condition,
n=26 committed decisions yielded AUROC 0.620; RCPS certified only α=0.30 at
δ=0.10 and δ=0.20 (coverage 1.0, observed error 0.038). The small sample does
not support a tighter risk claim.

**End-to-end.** In the retrospective eight-asset sickle-cell trajectory, the
integrated node shares the same N=8, post-reconciliation terminal result and
trivial-baseline caveats described in `docs/12_scd_vertical_slice.md`; detailed
per-record outputs are not released. The prospective example discussed in
`docs/12_scd_vertical_slice.md` has no terminal gold and is invalidated as
evidence because its source time context is stale; it is not a current
recommendation or prospectively validated calibration claim.

## Data sources

Open Targets Platform, ClinicalTrials.gov, openFDA, and EMA — all public. No
private or restricted data is used.

## Not included (release boundary)

Raw experiment scripts, per-record gold labels, run logs, and local paths are not
part of the public surface, consistent with `docs/release_boundary.md`.

## License

Apache-2.0.
