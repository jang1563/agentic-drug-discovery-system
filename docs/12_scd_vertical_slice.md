# SCD Vertical Slice — Validated Retrospective Benchmark + Prospective Demo

Date: 2026-07-04
Status: validated single-disease vertical slice; honest small-N scope

## Purpose

This document describes the one end-to-end **vertical slice** the project has
actually built and validated: a retrospective clinical/regulatory decision
benchmark on a single disease (**sickle cell disease**, MONDO_0011382), plus a
prospective decision-support demo built on the same flow. It is the concrete
instance behind the roadmap in `docs/11_full_flow_retrospective_and_prospective_plan.md`.

**Read the scope honestly first.** This is:

- a **retrospective decision benchmark** on **one disease and ~8 drug assets**,
- plus **one prospective decision-support demo** on a single ongoing asset,

and it is **NOT** a broad multi-disease atlas, **NOT** a validated clinical
predictor, and **NOT** an autonomous drug designer or wet-lab system. Its
outputs are grounded, verified, calibrated *decisions with an auditable evidence
trail* — never a claim of a validated clinical candidate. Only sickle cell
disease has a real end-to-end slice; breadth is roadmap, not built.

## What the slice is

An LLM agent traverses a fixed multi-stage discovery pipeline for each drug
asset. At every stage it emits exactly one decision from the action space
**advance / stop / defer / request_more_evidence / flag** (see
`chains/discovery_flow.py`). Evidence at each stage is **time-gated** — the agent
must not use later knowledge — and, in retrospective mode, the trajectory is
scored against the real historical outcome of that program.

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

**Five callable data-source tools** are exposed to the autonomous tool-use agent
(`chains/discovery_flow.py`, `Toolbox`): `opentargets_association`,
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
  runs live; otherwise, for a known ChEMBL drug it returns the clinically
  validated engagement *proxy* — explicitly labeled "not a Boltz prediction" —
  and for a de-novo candidate it returns unavailable and the agent defers or
  routes to compute.
- **RDKit molprops** (`molprops`) — QED, molecular weight, logP, H-bond
  donors/acceptors, and Lipinski violations. **Runs locally on CPU, no GPU.** It
  gives a real, computable druglikeness signal, so the SFM leg is not a pure
  GPU-only stub even on a clean clone.

In short: the SFM leg has both a GPU-gated structural predictor (Boltz-2) and a
local, no-GPU druglikeness signal (RDKit molprops).

## Asset roster (public identifiers only)

Eight assets, each defined by public identifiers only; adapters populate the
evidence. Every string below is a publishable public fact.

| Asset (public name) | Target symbol | Compound / target ID | Trial (NCT) | Regulatory ID |
| --- | --- | --- | --- | --- |
| voxelotor (Oxbryta) | HBB | CHEMBL4101807 (target CHEMBL2095168) | NCT03036813 (HOPE) | NDA213137 |
| crizanlizumab (Adakveo) | SELP | CHEMBL5378 | NCT01895361 (SUSTAIN), NCT03814746 (STAND) | BLA761128 |
| exa-cel / exagamglogene autotemcel (Casgevy) | BCL11A | — (CRISPR) | NCT03745287 (CLIMB) | FDA 2023-12-08 |
| L-glutamine (Endari) | — (metabolic) | — | NCT01179217 | NDA208587 |
| senicapoc | KCNN4 | — | NCT00294541 | investigational |
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

## Validated results — caveats first

**Read these caveats before any headline number:**

- **The "8/8" headline is N=8**, and it is measured *after* a boxed-warning gold
  reconciliation (one terminal flip, from 7/8 to 8/8). Several intermediate
  deltas are single-run or few-run against a self-authored weak-tree baseline,
  with **no confidence intervals and no seed sweeps**. Never headline 8/8 without
  this caveat.
- **Single disease, small-N.** Only sickle cell disease has a real end-to-end
  slice; the rest of the pipeline breadth is roadmap, not built.
- There is an estimated **~62% source-determinable ceiling** on the interpretive
  judgment axis: some calls (mixed-vs-stop, boxed-warning advance-vs-flag) are
  human judgment, not source-determined.
- Pathogen-target (neglected tropical) diseases fail stage 1, because Open
  Targets association is human-disease only.

**Construct validity holds.**

- On the 8-asset benchmark, **both trivial baselines fail** — always-advance =
  3/8, always-stop = 4/8 — while the LLM agent reaches **8/8 terminal-correct**
  (with the reconciliation and N=8 caveat above).
- The structural-tell shortcut was killed. A no-reasoning policy scored **96.8%
  on raw packets but collapses to 44.7% (= majority-class) on the
  allowlist-masked surface**, while a real reasoning policy still solves the
  masked surface (an evidence-reader baseline at 62.8%; an LLM at 65.4% clean on
  the locked hard set). Masking removes the shortcut without removing the signal.

**Memorization control held.** A name-scramble control (asset / brand / target
replaced by CANDIDATE / TARGET-X, evidence kept) held terminal accuracy at
**8/8 scrambled vs 8/8 original** (stage accuracy 72% vs 81%). The result
reflects reasoning over evidence, not recall of famous outcomes by name.

**Model-indistinguishability finding.** On the hard families at **n=153**, four
Claude models were **statistically indistinguishable** (overall 47.7–54.2%,
inside a ±8% binomial noise band, SE ≈ 4%). Small-N (12 per family) rankings did
**not** replicate at n=153. The lesson: quality is bounded by data/tool coverage
and honest labels, not by model reasoning — every large jump came from fixing
evidence, not swapping models. Practical consequence: a mid-tier model
(Sonnet-class) delivers near-top accuracy at roughly one-third the cost.

**Autonomous tool-use is higher-variance than the curated flow.** The curated
pre-gathered flow is **stable at 8/8** (81% stage accuracy); the autonomous
ReAct tool-use path is **noisy at 3–5/8 across runs (31–53% stage accuracy)** —
it over-flags known-safe drugs (hydroxyurea) and defers on approved positives
(exa-cel, L-glutamine). Honest framing: the reliable system is barely agentic;
the fully autonomous system is the noisy one.

**Calibration is certified only at loose risk levels.** A calibration card
exists (leave-one-out isotonic + RCPS, AUROC 0.80; auto-accepting the
lowest-risk 30% yields ~12% disagreement). A certified selective gate exists
**only at α ≥ 0.20** (13% coverage at 0% false-accept; 46% at ≤15%). A tight
gate at α ≤ 0.10 is **not** certifiable at n=298.

**Numbers safe to cite (aggregate):** trivial baselines 3/8 and 4/8; LLM 8/8
(with reconciliation + N=8 caveat); structural-tell 96.8% → 44.7%; scrambled
terminal 8/8; four-model overall 47.7–54.2% at n=153; curated 8/8 vs autonomous
3–5/8; calibration AUROC 0.80, certified only at α ≥ 0.20.

## Retrospective vs prospective modes

- **Retrospective** — evidence time-gated to historical decision points; the
  trajectory is scored against the known outcome. This is the benchmark.
- **Prospective** — the *same* flow and adapters with the time-gate set to NOW
  and no terminal gold. The demonstration asset is **mitapivat** (a PK-R
  activator, AG-348; target PKLR; CHEMBL4299940) for sickle cell disease, whose
  pivotal RISE UP trial (NCT05031780) is ongoing with no efficacy readout. The
  calibrated agent gathers current evidence via tools and returns **DEFER at all
  four stages**, synthesizing a **WATCH-AND-WAIT (medium confidence)**
  recommendation, with the load-bearing uncertainty stated explicitly (does PK-R
  activation translate to clinical benefit in SCD?). The output is decision
  **support** with provenance and calibrated uncertainty — explicitly **not** a
  validated drug and **not** an approval prediction.

## Reproduce

The slice is exercised through the shipped, tracked code:

- `chains/discovery_flow.py` — the action space, the `Toolbox` (five data-source
  tools), and the tool-use prompt/loop.
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
git diff --check
python3 -m compileall adapters chains scripts/audit
```

## Scope reminder

This slice is a decision + prioritization environment on one disease, not a
finished long-horizon agent platform. Do not read the 8/8 headline as validated
breadth: it is N=8, one disease, post-reconciliation, and the autonomous path is
higher-variance than the curated one. The value here is the *construct* — honest
source-derived labels, an enforced no-shortcut surface, and calibrated defer/stop
behavior — demonstrated on a single well-characterized disease.
