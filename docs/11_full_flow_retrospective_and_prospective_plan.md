# Full-Flow Plan — Retrospective Benchmark + Prospective Decision-Support

Date: 2026-07-02
Status: active plan; extends scope to include a prospective mode

## Purpose

Define how the Agentic Drug Discovery System becomes an environment where a user
can run a **full discovery decision flow for a specific disease and/or target**
— not just score isolated clinical/regulatory episodes. This document adds a
**prospective decision-support mode** to the project's scope alongside the
existing retrospective benchmark, and states the boundaries and guardrails for
both.

The system remains a **decision + prioritization environment**, NOT an
autonomous drug designer and NOT wet-lab automation. Its outputs are grounded,
verified, calibrated *decisions and prioritizations with an auditable evidence
trail* — never a claim of a validated clinical candidate.

## The full-flow chain

For a chosen disease and/or target, the agent traverses ordered stages, making a
terminal decision (`advance` / `stop` / `defer` / `request_more_evidence` /
`flag`) at each, carrying state, evidence, and calibrated uncertainty across
handoffs:

```
disease/target seed
  -> target identification / target-disease evidence      (Open Targets, UniProt, literature)   [milestone M4]
  -> modality / compound-target association                (ChEMBL, BindingDB, PubChem)          [M2]
  -> hit / structure / binder assessment                   (PDB, AlphaFold, Boltz-2, ESM)        [M5]
  -> lead optimization + ADMET / tox constraints           (TDC ADMET, tox assays)               [M3]
  -> cell / perturbation / phenotype reasoning             (DepMap, LINCS, State)                [M6]
  -> preclinical / IND -> clinical POC -> pivotal decision  (ClinicalTrials.gov, openFDA)         [M1]
```

Each stage = a set of episodes with a visible packet (what the agent sees) and,
in retrospective mode, a source-derived hidden gold (what actually happened).

## Two modes

### 1. Retrospective / benchmark mode (near-term, fully groundable)

Pick a disease/target with **history**. Replay the decision chain against real
CT.gov/FDA/DB outcomes. Measures whether the agent would have made good
advance/stop/defer decisions given the evidence available at each stage. Labels
come from the source-derived, no-human label authority (Track A). Safe,
reproducible, offline.

### 2. Prospective / decision-support mode (added scope, staged after retro is validated)

Point the flow at a **current** disease/target with open questions. The agent:

- retrieves current public evidence via tool/DB adapters (live or cached-refresh),
- calls SFMs as **fallible, low-weight soft scorers** (binding, structure,
  perturbation) — never as oracles,
- runs deterministic + soft verifiers on every intermediate claim,
- emits per-stage `advance / stop / defer / verify / flag` with **calibrated
  uncertainty**, an explicit **evidence-status vs probativeness** distinction,
  and a full **provenance trail**,
- **abstains / defers under uncertainty** rather than asserting.

Output = a ranked, uncertainty-annotated, auditable **decision-support dossier**
for the disease/target — an explicit hypothesis and recommendation set, not a
validated drug.

## Guardrails (apply to both modes, mandatory for prospective)

This project's north star is *safety infrastructure for scientific decision
agents* (epistemic control under delegation). Prospective mode must preserve:

- **trust / verify / defer / stop** as the control frame; the agent must be able
  to stop or request evidence rather than over-assert.
- **SFMs are soft prefilters, not authority.** Boltz-2 and perturbation FMs are
  fallible (weak/no correlation in lead-selection regimes; beaten by trivial
  baselines on some tasks) — low reward weight, per-target validation, never a
  deterministic gate.
- **No LLM-judge as sole authority.** Tool-based / deterministic verification is
  primary; LLM critique is diagnostic, multi-model, abstain-on-disagreement.
- **Uncertainty + provenance are infrastructure, not decoration** — every claim
  carries source, date, retrieval path, and a confidence/abstain state.
- **Decision-support boundary.** The system supports go/no-go/deprioritize
  reasoning and evidence synthesis. It is not a generative pipeline for novel
  hazardous design; it does not automate wet-lab execution. Fail-closed:
  unresolved / out-of-distribution -> defer or flag, never silent advance.
- **Responsible release.** Publish schemas, benchmarks, controls, and failure
  modes; do not ship a capability artifact.

## What must be built (gap from today)

For the clinical/regulatory decision layer (M1), the agent-loop half is now
**built and validated end-to-end on one disease** — sickle cell disease — with 7
tracked adapters and 2 flow orchestrators. See `docs/12_scd_vertical_slice.md`
for the concrete validated instance of this plan. The remaining roadmap stages
(M2–M6) are still unbuilt. To reach full flow:

1. **Honest source-derived labels per stage** — Track A (validated for M1);
   replicate the labeling-function + authority-table pattern for M2–M6.
2. **Live agent loop** — LLM planner (hosted model backend or API) + tool/DB
   adapters (CT.gov, openFDA, Open Targets, ChEMBL, PDB, …) + SFM scorers
   (GPU-gated Boltz-2/ESM plus a local no-GPU RDKit druglikeness signal). This
   half is implemented for the SCD slice; extending it across M2–M6 is the
   remaining work.
3. **Flow orchestrator (`chains/`)** — given a disease/target seed, assemble the
   ordered episode chain across stages and let the agent traverse it, carrying
   state/evidence/uncertainty across handoffs.
4. **Calibration layer** — conformal / RCPS / calibration cards so per-stage
   confidence and false-accept are bounded (prerequisite for prospective mode).

## First proof: thin vertical slice

Before building all of M2–M6, prove the concept with **one disease/target × 3
stages**:

- target-disease evidence (Open Targets) -> compound-target activity (ChEMBL) ->
  clinical decision (CT.gov, already Track-A labeled),
- one LLM policy + 2–3 tool adapters + one SFM (e.g., Boltz-2 binding score),
- agent traverses the 3 stages, emits per-stage decisions + provenance trail,
- **retrospective scoring first**; enable the prospective toggle only after the
  retrospective slice passes construct-validity (trivial baselines fail) and a
  calibration card exists.

## Sequencing

```
Track A (A1–A6): honest no-human source-derived labels + construct validity + calibration   [in progress]
  -> Track B: live agent loop + thin vertical slice (retrospective)                           [next]
  -> validate slice (Gate-7 + calibration) -> enable prospective toggle on the slice
  -> widen stages (M2–M6) and diseases/targets; refresh loop for live sources
```

Retrospective must be validated (labels honest, trivial baselines fail,
uncertainty calibrated) **before** the prospective mode is enabled for any
disease/target. Honest labels (Track A) are the trust foundation for the entire
flow.
