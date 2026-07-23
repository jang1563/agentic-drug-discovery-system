# SCD Vertical Slice — Audited Retrospective Benchmark + Prospective Scaffold

Date: 2026-07-12
Status: audited single-disease research slice; small-N; not clinical validation

## Purpose

This document describes the one end-to-end **vertical slice** the project has
actually built and audited: a retrospective clinical/regulatory decision
benchmark on a single disease (**sickle cell disease**, MONDO_0011382), plus an
unscored prospective scaffold built on the same flow. Its original example is
invalidated as evidence because it encoded a stale, mixed time context. This is
the concrete
instance behind the roadmap in `docs/11_full_flow_retrospective_and_prospective_plan.md`.

**Read the scope honestly first.** This is:

- a **retrospective decision benchmark** on **one disease and ~8 drug assets**,
- plus **one unscored prospective scaffold** whose stale example requires a new
  source-coherent run,

and it is **NOT** a broad multi-disease atlas, **NOT** a validated clinical
predictor, and **NOT** an autonomous drug designer or wet-lab system. Its
outputs are structured *decisions with an auditable evidence trail* — never a
claim of a validated clinical candidate. Only sickle cell
disease has a real end-to-end slice; breadth is roadmap, not built.

## What the slice is

An LLM agent traverses a fixed multi-stage discovery pipeline for each drug
asset. At every stage it emits exactly one decision from the action space
**advance / stop / defer / request_more_evidence / flag** (see
`chains/discovery_flow.py`). Curated retrospective packets carry an explicit
**time gate** and are intended to exclude later knowledge. The autonomous
tool-use path can call live adapters; the shipped code does **not** enforce a
historical cutoff for those live calls. A historically valid autonomous replay
therefore requires cutoff-safe cached adapters supplied by the evaluator.

The design goal is *epistemic control under delegation*: advance on strong early
evidence, differentiate on clinical-evidence quality, and **update to stop when
later regulatory evidence reverses an earlier call**. It is deliberately a thin,
depth-first slice — one disease, ~8 assets — not a broad atlas.

## Pipeline: 4 stages and their data adapters

| Stage | Name | Data source |
| --- | --- | --- |
| 1 | target–disease association | Open Targets |
| 2 | compound–target engagement | ChEMBL (molecule / mechanism / target-activity) |
| 3 | clinical | ClinicalTrials.gov (status, phase, results, whyStopped, primary-endpoint significance + direction) |
| 4 | regulatory | openFDA (FDA label + boxed warning) + EMA EPAR (EU status; catches reversals openFDA misses) |

**Six callable data-source operations across five sources** are exposed to the
autonomous tool-use agent (`chains/discovery_flow.py`, `Toolbox`):
`opentargets_association`,
`chembl_molecule` / `chembl_mechanism`, `ctgov_trial`, `fda_label`, `ema_epar`.

Two backend orchestration modes ship:

- a **curated pre-gathered flow** — evidence is pre-distilled per stage and the
  agent decides over it; and
- an **autonomous tool-use ReAct loop** — the LLM issues its own tool calls under
  a bounded call budget.

## SFM tools (structure / property leg)

Two structure/property tools support the compound-design leg:

- **Boltz-2** (`boltz2`) — predicted binding affinity + structure confidence.
  **GPU-gated.** It uses a tiered, honest fallback: if a GPU endpoint is
  configured (set the `BOLTZ_ENDPOINT` environment variable to a GPU service) it
  runs live; otherwise, for a known ChEMBL drug it returns a ChEMBL
  development-stage/mechanism metadata *proxy*. That proxy is explicitly labeled
  "not a Boltz prediction" and does not validate target engagement. For a
  de-novo candidate it returns unavailable and the agent defers or routes to
  compute.
- **RDKit molprops** (`molprops`) — QED, molecular weight, logP, H-bond
  donors/acceptors, and Lipinski violations. **Runs locally on CPU when RDKit is
  installed; no GPU is required.** It provides a computable druglikeness signal
  without representing a binding or clinical prediction.

In short: the SFM leg has both a GPU-gated structural predictor (Boltz-2) and a
local, no-GPU druglikeness signal (RDKit molprops).

## Asset roster (public identifiers only)

Eight assets, each defined by public identifiers only; adapters populate the
evidence. Every string below is a publishable public fact.

| Asset (public name) | Target symbol | Compound / target ID | Trial (NCT) | Regulatory ID |
| --- | --- | --- | --- | --- |
| voxelotor (Oxbryta) | HBB | CHEMBL4101807 (target CHEMBL2095168) | NCT03036813 (HOPE) | NDA213137 |
| crizanlizumab (Adakveo) | SELP | CHEMBL4297734 (target CHEMBL5378) | NCT01895361 (SUSTAIN), NCT03814746 (STAND) | BLA761128 |
| exa-cel / exagamglogene autotemcel (Casgevy) | BCL11A | — (CRISPR) | NCT03745287 (CLIMB) | FDA 2023-12-08 |
| L-glutamine (Endari) | — (metabolic) | — | NCT01179217 | NDA208587 |
| senicapoc | KCNN4 | CHEMBL405821 (target CHEMBL4305) | NCT00294541 | investigational |
| rivipansel (GMI-1070) | SELE | — | NCT02187003 (RESET) | investigational |
| hydroxyurea (Droxia/Siklos) | RRM1 | CHEMBL467 | NCT00000586 | NDA016295, NDA208843 |
| Lyfgenia (lovotibeglogene autotemcel) | HBB | CHEMBL4650269 | NCT02140554 | BLA125788 |

**Aggregate terminal-decision mix (8 assets): 4 stop / 3 advance / 1 flag.** The
mix is engineered so that both trivial policies — always-advance and
always-stop — necessarily fail. (Which asset maps to which terminal is
reconstructable from public regulatory history — for example, the Lyfgenia
hematologic-malignancy boxed warning is the `flag` case — so publishing the
aggregate mix is safe. The per-stage gold-label arrays are evaluator-only and
are **not** published here.)

## Audited results — caveats first

**Read these caveats before any headline number:**

- **The "8/8" headline is N=8**, and it is measured *after* a boxed-warning gold
  reconciliation (one terminal flip, from 7/8 to 8/8). Several intermediate
  deltas are single-run or few-run against a self-authored weak-tree baseline,
  with **no confidence intervals and no seed sweeps**. Never headline 8/8 without
  this caveat.
- **Single disease, small-N.** Only sickle cell disease has a real end-to-end
  slice; the rest of the pipeline breadth is roadmap, not built.
- A deterministic evidence reader covered **62.8%** on a separate constructed
  Track-A packet surface. That is an observed baseline on that surface, not a
  fundamental source-determinability ceiling.
- Pathogen-target (neglected tropical) diseases fail stage 1, because Open
  Targets association is human-disease only.

**Scoped construct-validity controls.**

- On the 8-asset benchmark, **both trivial baselines fail** — always-advance =
  3/8, always-stop = 4/8 — while the LLM agent reaches **8/8 terminal-correct**
  (with the reconciliation and N=8 caveat above).
- In a **separate Track-A diagnostic over n=298 packets** (not the eight-asset
  SCD slice and not the external Hugging Face benchmark), a no-reasoning
  structural heuristic scored **80.5% on raw packets and 32.9% after
  allowlist masking**, equal to the majority-class floor. A deterministic
  evidence reader scored 62.8% and one local LLM aggregate scored 65.4% on the
  masked surface, both above the 32.9% floor. These are local aggregate controls;
  the packet-level data and run outputs do not ship.

**Name-scramble control.** In a single local run, replacing asset / brand /
target names with CANDIDATE / TARGET-X while retaining evidence kept terminal
accuracy at **8/8 scrambled vs 8/8 original**; stage accuracy changed from 81%
to 72%. This control is compatible with evidence use, but one run does not rule
out memorization generally.

**Model comparison did not resolve a stable ordering.** On the hard families at
**n=153**, four Claude models ranged from **47.7% to 54.2%** overall. A separate
paired common set at n=186 found no significant pairwise difference, but did
not establish ±5-point equivalence. The public artifact therefore makes no
model-ranking or cost-ratio claim; cost was not measured in the released
aggregate evidence.

**Fixed-slice prompt regression.** The released prompt distinguishes a program
that is halted, withdrawn, or revoked (`stop`) from a still-approved/on-market
asset with a serious safety signal (`flag`). After that correction, a local
pre-release regression repeated the **same fixed eight assets 10 times per
policy**: curated **80/80** and autonomous tool-use **80/80** terminal-correct
(descriptive Wilson 95% interval 95.4–100.0% for each set of repeated
observations). This is a regression check on one fixed slice, not independent
sampling, general autonomous reliability evidence, or clinical validation. The
autonomous branch used present-day source lookups and is not evidence of a
historically time-gated, leakage-controlled replay.

**Calibration targets a label-uncertainty proxy, not clinical truth.** On the
separate n=298 Track-A packet surface, a leave-one-out isotonic risk signal had
AUROC **0.80** against disagreement between auto-assigned labels and an
independent deterministic evidence reader. Empirically, the lowest-risk 30%
(n=89) had 12.4% disagreement. At δ=0.10, RCPS certificates begin at α=0.20:
12.8% coverage with 0% observed disagreement; α=0.25 gives 45.6% coverage with
14.7% observed disagreement. No α≤0.15 certificate exists at δ=0.10. These
numbers do not validate label truth or prospective clinical decisions.

**Audited aggregate numbers:** trivial baselines 3/8 and 4/8; curated LLM 8/8
(post-reconciliation and N=8); separate Track-A packet heuristic 80.5% → 32.9%
at n=298; single-run scrambled terminal 8/8; four-model range 47.7–54.2% at
n=153; fixed-slice prompt regression 80/80 per policy over 10 repeats; and
Track-A label-proxy AUROC 0.80 with the δ/α limits above. The machine-readable
counterpart is `docs/public_evidence_summary.json`.

## Retrospective vs prospective modes

- **Retrospective** — curated packets or evaluator-supplied cutoff-safe adapters
  are time-gated to historical decision points, and the trajectory is scored
  against the known outcome. Live adapter calls alone do not satisfy this gate.
- **Prospective scaffold** — the unscored mitapivat example (PKLR;
  CHEMBL4299940; NCT05031780) encoded a stale no-readout assumption after an
  [official topline readout had been published on
  2025-11-19](https://investor.agios.com/news-releases/news-release-details/agios-announces-topline-results-rise-phase-3-trial-mitapivat).
  Its time context is incoherent, so the example is **invalidated as evidence**;
  any previously reported watch/defer output is withdrawn from citation. It has
  no terminal gold or dated public run artifact and must be source-refreshed and
  rerun before reuse. It is scaffolding — explicitly **not** a current
  recommendation, validated drug, clinical advice, or approval prediction.

## Reproduce

The slice is exercised through the shipped, tracked code:

- `chains/discovery_flow.py` — the action space, the `Toolbox` (six operations
  across five data sources), and the tool-use prompt/loop.
- `chains/episode_flow.py` — per-episode flow orchestration.
- `adapters/opentargets_adapter.py`, `adapters/chembl_adapter.py`,
  `adapters/ctgov_adapter.py`, `adapters/ema_epar_adapter.py`,
  `adapters/ema_ledger.py` — the five stage data adapters.
- `adapters/boltz_adapter.py` — GPU-gated Boltz-2 SFM tool with honest fallback.
- `adapters/molprops_adapter.py` — local (CPU) RDKit druglikeness signal.
- `rl_env/specs/` — state, action, observation, and case-bank schema sketches.

**Data boundary (important for reproduction):** the adapter *code* ships, but the
cached data snapshots and evaluation case banks it reads from do **not** ship —
those trees are excluded from the public release surface by design (see
`docs/release_boundary.md`). On a clean public clone the adapters therefore
import and compile but are **illustrative-only**: they cannot pull live evidence
without a user supplying their own cached snapshots or live API access, and the
Boltz-2 tool requires a GPU endpoint (`BOLTZ_ENDPOINT`) to run live. Evaluator-only
gold labels, locked replay episodes, and generated run outputs are intentionally
withheld.

To run the audit gate locally before committing changes to this surface:

```
python3 scripts/audit/github_release_file_audit.py
python3 scripts/audit/validate_hf_release_package.py
python3 scripts/audit/validate_public_launch_packet.py
python3 scripts/audit/validate_vertical_slice_doc.py
python3 -m pytest -q benchmark/tests
python3 scripts/audit/build_hf_release_package.py --output /tmp/agentic-hf-release-package --force
python3 scripts/audit/validate_hf_release_package.py --package /tmp/agentic-hf-release-package
git diff --check
python3 -m compileall adapters chains benchmark/src scripts/audit
```

## Scope reminder

This slice is a decision + prioritization environment on one disease, not a
finished long-horizon agent platform. Do not read the 8/8 headline as validated
breadth: it is N=8, one disease, and post-reconciliation. The 80/80 results are a
repeated regression on the same assets, not a new validation set. The value here
is the inspectable control design — source-derived labels, a masked packet
surface, and explicit defer/stop behavior — demonstrated on a single
well-characterized disease.
