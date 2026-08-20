# Full-Flow Plan — Retrospective Benchmark + Prospective Decision-Support

Date: 2026-08-20
Status: one audited SCD slice, generic M6 handoff, and synthetic UC conformance; prospective mode remains unscored decision support

## Purpose

Define how the Agentic Drug Discovery System becomes an environment where a user
can run a **full discovery decision flow for a specific disease and/or target**
— not just score isolated clinical/regulatory episodes. This document adds a
**prospective decision-support mode** to the project's scope alongside the
existing retrospective benchmark, and states the boundaries and guardrails for
both.

The system remains a **decision + prioritization environment**, NOT an
autonomous drug designer and NOT wet-lab automation. Its outputs are grounded,
structured *decisions and prioritizations with an auditable evidence
trail* — never a claim of a validated clinical candidate.

## The full-flow chain

For a chosen disease and/or target, the agent traverses ordered stages, making a
terminal decision (`advance` / `stop` / `defer` / `request_more_evidence` /
`flag`) at each, carrying state, evidence, and an explicit uncertainty state across
handoffs:

```
disease/target seed
  -> target identification / target-disease evidence      (Open Targets, UniProt, literature)   [milestone M4]
  -> modality / compound-target association                (ChEMBL, BindingDB, PubChem)          [M2]
  -> hit / structure / binder assessment                   (PDB, AlphaFold, Boltz-2, ESM)        [M5]
  -> lead optimization + ADMET / tox constraints           (TDC ADMET, tox assays)               [M3]
  -> cell / perturbation / phenotype reasoning             (generic handoff built; atlas open)  [M6]
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

### 2. Prospective / decision-support mode (added scope, staged after retrospective audit)

Point the flow at a **current** disease/target with open questions. The agent:

- retrieves current public evidence via tool/DB adapters (live or cached-refresh),
- calls SFMs as **fallible, low-weight soft scorers** (binding, structure,
  perturbation) — never as oracles,
- runs deterministic + soft verifiers on every intermediate claim,
- emits per-stage `advance / stop / defer / verify / flag` with an explicit
  uncertainty state and **evidence-status vs probativeness** distinction,
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
  modes; ship only the limited decision-prototype surface, not a complete
  autonomous discovery or wet-lab capability.

## What must be built (gap from today)

For the clinical/regulatory decision layer (M1), the agent-loop half is now
**built and audited end-to-end on one disease** — sickle cell disease — with 7
tracked adapters and 2 flow orchestrators. See `docs/12_scd_vertical_slice.md`
for the concrete audited instance of this plan. A small-N target-identification
node prototype (M4) is documented in `docs/13_target_id_governance_node.md`. A generic, strict M6
cell-state and perturbation handoff is implemented in
`docs/40_upstream_translational_handoff.md`, but it contains only a synthetic fixture and cannot
promote mechanism or efficacy. Integrated M2, M3, and M5 atlases, an externally reviewed M6
fixture, real cross-disease orchestration, and external transport remain unbuilt. A synthetic UC
conformance slice now verifies higher-is-better remission-ratio semantics across M6 and clinical
contracts, but it is not a second validated vertical slice. To reach full flow:

1. **Honest source-derived labels per stage** — Track A is audited for M1 and a
   small-N M4 node exists; replicate the labeling-function + authority-table
   pattern for broader M2–M6 atlases and one independent immune or inflammatory disease slice.
2. **Live agent loop** — LLM planner (hosted model backend or API) + tool/DB
   adapters (CT.gov, openFDA, Open Targets, ChEMBL, PDB, …) + SFM scorers
   (GPU-gated Boltz-2/ESM plus a local no-GPU RDKit druglikeness signal). This
   half is implemented for the SCD slice. M6 now has a payload-minimized contextual handoff, but
   live source adapters and integrated M2, M3, M5, and M6 atlases remain open.
3. **Flow orchestrator (`chains/`)** — given a disease/target seed, assemble the
   ordered episode chain across stages and let the agent traverse it, carrying
   state/evidence/uncertainty across handoffs.
4. **Calibration layer** — outcome-free cohort diagnostics, preregistered outcome contracts,
   dependence-aware uncertainty, and synthetic known-truth stress/calibration studies are
   implemented. A real independently curated held-out board, external transport study, conformal
   or RCPS guarantees, and stage-specific calibration cards remain required before prospective
   mode can be treated as scored or operational.

## Implemented first proof: thin vertical slice

The current proof uses **one disease/target × 3 stages** and remains a thin
slice rather than the full M2–M6 system:

- target-disease evidence (Open Targets) -> compound-target activity (ChEMBL) ->
  clinical decision (CT.gov, already Track-A labeled),
- one LLM policy + 2–3 tool adapters + one SFM (e.g., Boltz-2 binding score),
- agent traverses the 3 stages, emits per-stage decisions + provenance trail,
- **retrospective scoring first**; enable the prospective toggle only after the
  retrospective slice passes construct-validity (trivial baselines fail) and a
  calibration card exists.

## Sequencing

```
Track A (A1–A6): source-derived labels + scoped controls + retrospective risk analysis       [audited locally]
  -> Track B: live agent loop + thin SCD vertical slice                                       [audited locally]
  -> synthetic UC M6-to-clinical ratio-direction conformance                                  [implemented]
  -> validate one independently reviewed external M6 handoff without unsupported promotion     [next]
  -> join an independent held-out outcome board and external transport study before scored use
  -> widen M2/M3/M5 atlases and disease/target breadth; refresh loop for approved live sources
```

Retrospective evidence must be cutoff-safe and audited (labels honest, trivial
baselines fail, uncertainty calibrated against the stated target) **before**
prospective mode is treated as scored or operational for any disease/target.
The currently shipped prospective example is unscored scaffolding.
