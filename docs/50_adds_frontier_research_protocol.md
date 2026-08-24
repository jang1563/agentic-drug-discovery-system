# ADDS-Frontier Research Protocol

Date: 2026-08-21

Status: 10 calibration drafts commitment-bound; automated scorer replay 60/60 and machine-decidable probes 30/30; oracle fragility localization 296/296 but support revision required; 130 support-curation occurrences compiled into 110 review candidates and 20 protected singletons; 50 canonical transitions contain 20 action-only, 20 access/witness-only, 10 stable, and zero coupled action/support changes; 10 matched evidence-reveal/control units, 10 canonical/candidate/placebo triplets, and 10 five-arm tokenizer-control packets compiled with zero semantic labels or admissions; 20 semantic packets and 10 independent-oracle challenge packets compiled but unassigned; all human review, board admission, and model runs remain pending

Machine contract: `docs/adds_frontier_research_protocol.json`

## Flagship question

> Can a scientific agent acquire and synthesize sufficient time-valid,
> lineage-aware evidence to earn each state transition in a long-horizon
> drug-discovery trajectory without relying on final-outcome recall?

The central distinction is between **epistemic authorization** and **future
outcome correctness**. An action can be justified by the evidence available at
the decision time and still turn out poorly. Conversely, a model can recall or
guess the eventual outcome while using stale, derivative, mismatched, or
post-cutoff evidence. The latter is not a successful scientific trajectory.

This protocol turns that distinction into a frontier evaluation rather than a
presentation claim. Existing high-accuracy fixed-slice results remain regression
and diagnostic controls; they are not the flagship endpoint.

## Primary endpoint

The primary metric is **Fully Authorized Trajectory Success at pass@1**. One
trajectory passes only when all mandatory gates pass and the evaluator records
zero unauthorized commits. A correct final disposition cannot compensate for a
failed intermediate gate.

The mandatory gates are:

1. complete required evidence retrieval;
2. identity continuity;
3. cutoff compliance;
4. evidence-lineage independence;
5. endpoint and population alignment;
6. explicit uncertainty handling;
7. correct disposition;
8. correct bounded next action;
9. correct risk flags;
10. a valid evidence witness;
11. a valid blocker certificate;
12. budget compliance; and
13. exact replay.

The factorized action is:

- `disposition`: `advance`, `hold`, or `terminate`;
- `next_action`: `retrieve`, `verify`, `experiment`, `human_review`, or `none`;
- `risk_flags`: zero or more of `safety`, `contradiction`, `provenance`,
  `out_of_distribution`, and `temporal_leakage`.

This replaces the incompatible action vocabularies currently used by the legacy
SCD flow, core program state, and external clinical-trial scorer for new
ADDS-Frontier work. Legacy outputs retain their original semantics and require an
explicit adapter before comparison.

## Frontier difficulty contract

The launch observation target is a best-frontier-agent pass@1 rate between 0.5%
and 5%, centered near 2%. This band is **not** a task-selection rule. Tasks must be
sampled and frozen before baseline model runs. Items cannot be retained, removed,
or edited because a model passed or failed them.

Low performance is scientifically interpretable only if:

- an independent expert can solve the task with the same evidence world and
  adequate time;
- a structured oracle passes at least 95%;
- the environment exposes sufficient evidence and tool budget;
- scoring ignores arbitrary formatting differences;
- failures can be localized to meaningful scientific gates; and
- model, scaffold, tool access, cost, wall time, and pass@k are reported.

If every frontier system scores zero, the task surface is not automatically a
successful benchmark. The pilot must determine whether zero reflects genuine
capability limits, broken tasks, an inadequate environment, or an excessively
brittle scoring rule.

## Two evaluation tiers

### Diagnostic tier

One to three stages isolate retrieval, identity, chronology, lineage, mapping,
action, and replay failures. These tasks provide a learning signal and explain
where a full trajectory failed. Diagnostic accuracy is secondary and cannot be
substituted for frontier success.

### Frontier tier

Six to twelve interactive stages require evidence acquisition, source and state
updates, contradiction handling, bounded action selection, and replay in one
trajectory. The agent receives a common frozen environment and a fixed budget.
This tier supplies the primary leaderboard.

## Five task families

| Family | Capability boundary | Current design seed |
|---|---|---|
| Evidence Lineage Trap | Distinguish multiple files from independent underlying evidence | Preclinical lineage and source-disjoint RA synthesis |
| Temporal Reversal | Use only evidence available at the declared cutoff and update when later evidence becomes admissible | SCD stale prospective example and sealed cutoff-safe evaluation |
| Translational Handoff | Preserve disease, target, perturbation, model-system, and claim identity without unsupported promotion | Generic M6 handoff |
| Non-Exchangeable Replication | Refuse invalid pooling or transport across population, phase, endpoint, timeframe, or estimand differences | RA population, replication, and risk-of-bias ladder |
| Budgeted Evidence Resolution | Select the bounded action most likely to resolve a decision-relevant blocker | Clinical evidence tensor, bounded VOI, and closed loop |

The checked-in seed manifest provides one design-only seed per family. It does
not contain five benchmark tasks and is not performance evidence.

## Public development tranche

The first executable curation tranche contains one **public development fixture**
per family. Model-visible tasks, evaluator oracles, and curation status are stored
as separate hash-bound artifacts. The validator enforces artifact bytes,
monotone cutoff chronology, cumulative evidence access, acyclic lineage graphs,
6-12 stages, exact tool budgets, stage-by-stage factorized actions, and all 25
seed-bound counterfactual mutations.

These five fixtures are intentionally unsuitable for leaderboard evaluation:
their oracles are public, independent scientific and leakage review remain
pending, no curator roster is claimed, and every `board_admitted` value is
false. They exercise the benchmark machinery but contribute **zero** tasks to
the 40-task private pilot target.

- Model-visible tasks:
  `rl_env/specs/frontier_development_task_set.example.json`
- Public contract oracle:
  `rl_env/specs/frontier_development_oracle_set.example.json`
- Curation state:
  `rl_env/specs/frontier_development_curation_tranche.example.json`

## Private board sampling frame

The private pilot is preregistered as a 5-family by 8-domain grid: hematology,
immune-inflammatory disease, oncology, neurology, metabolic disease, infectious
disease, cardiovascular disease, and rare genetic disease. Each family receives
eight slots. The 10 hematology and immune-inflammatory slots form a calibration
partition aligned with current repository strengths; the other 30 slots remain
sealed evaluation across six less-developed domains.

Temporal allocation is also frozen before authoring: 15 pre-2024 historical
tasks, 15 tasks with 2024-2025 cutoffs, and 10 contemporary-2026 tasks. Exact
disease, program, task, oracle, curator, and canary identities remain private.
Every task requires three independent curators and ten admission gates, including
lineage and leakage review, expert solvability, structured-oracle replay, conflict
clearance, and contamination-canary review.

The checked-in 40-slot registry is deliberately an immutable, unpopulated
preregistration snapshot. A separate payload-free progress manifest now binds
10 private calibration task/oracle drafts: one hematology and one
immune-inflammatory task for every family, totaling 60 stages and 50 mutations.
Only packet-integrity and oracle-sealing gates are marked `pass`. Independent
scientific, lineage, leakage, mutation, expert-solve, replay, conflict, and
contamination review remain `pending`; curator count, board admission, and model
runs remain zero. These are authored drafts, not benchmark evidence.

- Board protocol: `docs/adds_frontier_board_protocol.json`
- Unpopulated slot registry:
  `rl_env/specs/frontier_private_board_slots.example.json`
- Payload-free authoring progress:
  `rl_env/specs/frontier_calibration_authoring_progress.json`
- Public progress schema:
  `rl_env/specs/frontier_calibration_authoring_progress.schema.json`
- Private task/oracle schemas (contracts only; payloads excluded):
  `rl_env/specs/frontier_private_calibration_task_set.schema.json` and
  `rl_env/specs/frontier_private_calibration_oracle_set.schema.json`

Public validation does not require private bytes:

```bash
adds-frontier validate-calibration
```

Maintainers can open every public commitment against the ignored local packet
and oracle files without publishing them:

```bash
adds-frontier validate-private-calibration
```

### Automated calibration preflight

The authored calibration packets have an executable, deterministic preflight that does not consume
or satisfy human-review gates. It replays the six canonical stage expectations for each of the ten
drafts through the five-component scorer and executes five frozen probes per task:

- `source_id_rename`, `critical_evidence_removal`, and `temporal_access_rebind` are
  machine-decidable contract probes; all 30 produce their preregistered structural outcome.
- `bounded_evidence_reveal` and `identity_rebind` are semantic-review probes. All 20 remain
  structurally valid, demonstrating that schema validity alone cannot establish the changed
  disposition, next action, risk flags, witnesses, or blockers.

Canonical scorer round-trip is `60/60`. This is self-consistency of authored labels with the scorer,
not independent scientific correctness or expert solvability. The public summary contains only
aggregate counts and a commitment to the ignored detailed report:

- Public summary: `rl_env/specs/frontier_calibration_preflight_summary.json`
- Public summary schema: `rl_env/specs/frontier_calibration_preflight_summary.schema.json`
- Private-report schema: `rl_env/specs/frontier_private_calibration_preflight.schema.json`

```bash
adds-frontier validate-preflight
adds-frontier summarize-preflight
adds-frontier validate-private-preflight  # maintainer environment only
```

### Blinded semantic-review readiness

The 20 structurally accepted semantic probes are materialized into private two-arm draft packets.
Arm order is deterministically blinded from private oracle nonces. Reviewer packets contain task
evidence for both arms but no canonical-arm mapping, stage oracle, or author-expected component
changes. A separate private key set binds those fields without exposing them to reviewers.

Every packet has an exact minimal-delta certificate. Evidence-ladder pairs add one independent
synthetic counterfactual evidence node, reveal it only from stage 4 onward, and alter no existing
node or non-access stage field. Identity pairs alter only `program_identity` using a unique hybrid
identity. All materialized tasks replay through the private task/oracle structural validators.

The public readiness summary commits to both private sets and reports `20/20` exact structural
deltas, but zero reviewer assignments, responses, consensus labels, and adjudications. Synthetic
counterfactual text is task material, not a factual source, and structural exactness is not a
semantic judgment.

```bash
adds-frontier validate-semantic-review
adds-frontier summarize-semantic-review
adds-frontier validate-private-semantic-review  # maintainer environment only
```

### Response triage and adjudication routing

Each packet requires exactly three unique reviewer commitments. Every response binds the packet
set, both arm commitments, all six stages, reviewer and affiliation commitments, conflict status,
and independence attestation. Free-form conclusions are replaced by structured actions, witnesses,
blockers, changed components, and bounded reason codes.

Before disagreement routing, the validator derives disposition, next-action, risk-flag, witness,
and blocker deltas directly from the two six-stage answer sequences. For a non-abstaining response,
the declared `semantic_change_detected` and `changed_components` must equal those observed deltas.
A narrative cannot claim a change absent from the stage answers or hide a change present in them.

For `bounded_evidence_reveal`, all action and support outputs must remain identical before the
first stage where arm-level `accessible_evidence_ids` diverge. This is a temporal causal boundary:
evidence visible only at a later stage cannot alter an earlier answer. Changed evidence-reveal
responses require an evidence eligibility, sufficiency, lineage, or uncertainty reason;
`identity_rebind` changes require `identity_discontinuity`.

The deterministic triage precedence is:

1. any stage or pair abstention -> human adjudication;
2. disposition, next-action, or risk-flag disagreement -> action adjudication;
3. witness or blocker disagreement -> support adjudication;
4. semantic-change or changed-component disagreement -> change adjudication; and
5. three exact responses -> consensus candidate only.

A consensus candidate cannot alter a board gate. It still requires unblinding, structured-oracle
replay, conflict review, and the frozen admission process. The current private ledger contains 20
unassigned records and zero assignments, responses, consensus candidates, or adjudications. The
public summary commits to that ledger without publishing reviewer workflow bytes.
Pair-delta equality and pre-access invariance are machine-decidable consistency constraints. They
do not establish that a consensus label or private oracle is scientifically correct.

```bash
adds-frontier validate-semantic-workflow
adds-frontier summarize-semantic-workflow
adds-frontier validate-private-semantic-workflow  # maintainer environment only
```

### Sealed unblinding and canonical resolution replay

Triage is not permission to inspect the private key. Unblinding requires the original three
responses to recompute exactly to `consensus_candidate`; the triage, response commitments, packet
set, key set, canonical task, and private oracle are then opened in sequence. Any incomplete,
rebound, or non-consensus input fails closed before canonical-arm identity is returned.

The canonical arm is replayed over all six stages using the five factorized scorer components:
disposition, next action, risk flags, witness set, and blocker certificate. This yields 30 private
checks. Exact replay routes to `canonical_replay_pass_resolution_receipt_pending`; any mismatch
routes to `adjudication_required_canonical_replay_failure`. Both routes retain
`board_gate_changed=false`.

A private resolution receipt binds the triage, three responses, unblinding identity, replay, human
identity and affiliation commitments, conflict and independence attestations, bounded rationale,
and decision. Failed replay cannot be accepted as consensus. A valid receipt still only permits
admission review; it cannot update a board gate by itself.

The current resolution ledger contains 20 `awaiting_reviewer_responses` records and zero
unblindings, replays, receipts, or admissions. The public summary contains only aggregate state,
frozen rules, and a commitment to the excluded ledger. Synthetic pass/failure tests demonstrate
contract behavior but are not live review or adjudication evidence.

```bash
adds-frontier validate-semantic-resolution
adds-frontier summarize-semantic-resolution
adds-frontier validate-private-semantic-resolution  # maintainer environment only
```

### Oracle fragility and support selectivity

Before independent challengers are assigned, a machine-only audit perturbs each of the five scorer
components at every canonical stage. Each probe remains valid under `FrontierAction` grammar and
must fail exactly its targeted score component while all other components pass. Of 300 planned
probes, 296 are applicable and all 296 localize exactly; four next-action probes are structurally
nonapplicable because a `terminate` disposition requires `next_action=none`.

Localization establishes scorer factorization only. The same audit detects support structures that
require scientific curation without deciding which evidence is correct or necessary. The current
private report finds:

- `60/60` witness-saturated stages and zero accessible non-witness evidence items;
- `10/10` tasks witness-saturated at every stage;
- seven stages with multiple witness IDs from one lineage;
- `60/60` singleton blocker certificates; and
- 20 action changes without witness-set change and 20 witness-set changes without action change.

The frozen task-wide saturation and repeated-lineage triggers therefore set
`oracle_support_ready_for_independent_challenge=false` and `human_curation_required=true`.
Challenge contracts may remain compiled, but assignment is blocked until revised private oracles
rerun this audit without those triggers. Machine checks neither establish scientific minimality nor
change expert-solve or board-admission gates.

- Public summary: `rl_env/specs/frontier_oracle_fragility_summary.json`
- Public schema: `rl_env/specs/frontier_oracle_fragility_summary.schema.json`
- Private-report schema: `rl_env/specs/frontier_private_oracle_fragility_report.schema.json`

```bash
adds-frontier validate-oracle-fragility
adds-frontier summarize-oracle-fragility
adds-frontier validate-private-oracle-fragility  # maintainer environment only
```

### Machine-prepared support curation

Because human review is not yet available, the next machine-only step prepares bounded review
work rather than changing labels. Every canonical witness occurrence receives a deterministic
record bound to its task, oracle, preflight, and fragility commitments. A leave-one-out
counterfactual is generated only when at least one witness remains.

The current workload contains 130 witness occurrences. Twenty singleton occurrences are protected
as nonapplicable. The remaining 110 produce exact witness-only scorer failures, partitioned into 14
repeated-lineage member candidates and 96 other saturation/selectivity candidates. Occurrence roles
are 85 source, 8 context, 4 contradiction, 7 derivative, and 26 decision-record references. Role
counts prioritize inspection only and do not rank scientific value.

Each private candidate retains its evidence and lineage IDs, role, reason codes, leave-one-out
witness set, and five-component score vector. The public artifact exposes only aggregate workload
counts and a private packet-set commitment. It fixes all of the following to false: scientific
removal support, automatic oracle edits, oracle support readiness, challenge assignment, expert
gate change, and board admission. Human assignment and decision counts remain zero.

- Public summary: `rl_env/specs/frontier_oracle_support_curation_summary.json`
- Public schema: `rl_env/specs/frontier_oracle_support_curation_summary.schema.json`
- Private packet schema: `rl_env/specs/frontier_private_oracle_support_curation_packet_set.schema.json`

```bash
adds-frontier validate-support-curation
adds-frontier summarize-support-curation
adds-frontier validate-private-support-curation  # maintainer environment only
```

### Cross-stage causal discriminability audit

The canonical six-stage trajectories contain 50 adjacent transitions. The machine audit compares
exact action components, witness sets, blocker sets, accessible evidence, required gates, stage
kinds, and dates between each pair. It preserves every private delta in a commitment-bound report
but does not infer a scientific cause.

The observed transition partition is:

- 20 action changes without witness or accessible-evidence change;
- 20 witness/access changes without action change;
- 10 stable action/witness transitions, all entering replay; and
- zero transitions with both action and witness change.

All 20 newly accessible evidence items are added to the witness set exactly. All 20 action changes
occur without an accessibility delta and coincide with blocker changes. Required gate sets change
at all 50 transitions; dates change at two. Across action components, next action changes 20 times,
risk flags eight times, and disposition four times.

This factorization is not an inconsistency verdict. Stage/gate progression may justify action and
blocker changes, while newly visible evidence may be confirmatory rather than decision-changing.
However, because action changes and evidence-access changes both occur but never co-occur, the
canonical trajectories cannot directly identify evidence-responsive action change. The public
summary therefore sets `canonical_transition_coupling_coverage_ready=false`,
`evidence_action_coupling_review_required=true`, and
`scientific_causality_established=false`. No oracle edit or challenge assignment is authorized.

- Public summary: `rl_env/specs/frontier_oracle_transition_audit_summary.json`
- Public schema: `rl_env/specs/frontier_oracle_transition_audit_summary.schema.json`
- Private-report schema: `rl_env/specs/frontier_private_oracle_transition_audit_report.schema.json`

```bash
adds-frontier validate-transition-audit
adds-frontier summarize-transition-audit
adds-frontier validate-private-transition-audit  # maintainer environment only
```

### Controlled evidence-action augmentation design

The transition audit's zero-coupling result defines a coverage problem, not an oracle-edit rule.
The next experiment is therefore compiled as ten matched design units. Each unit binds one existing
blinded `bounded_evidence_reveal` semantic packet to the same calibration slot's
`source_id_rename` nuisance-invariance probe.

The candidate arm is structurally exact: one independent evidence node is added, evidence access
changes only from stage 4 onward, and no existing node, lineage edge, non-access stage field, or
other task field changes. The matched control changes evidence identifiers throughout the task and
oracle while preserving a valid invariant contract outcome. All ten candidates and all ten
controls pass these machine-decidable design checks.

The private key shows that every selected candidate was authored to test both next-action and
witness change. That expectation is sealed selection metadata, not an observed semantic label.
The public artifact consequently records `coupled_augmentation_design_ready=true` while keeping
`semantic_label_recorded_count=0`, `coupled_transition_admitted_count=0`,
`scientific_coupling_established=false`, and
`canonical_transition_coupling_coverage_ready=false`. No candidate can become calibration data
without the existing independent semantic-review workflow and later board gates.

- Public summary: `rl_env/specs/frontier_coupled_augmentation_summary.json`
- Public schema: `rl_env/specs/frontier_coupled_augmentation_summary.schema.json`
- Private packet schema: `rl_env/specs/frontier_private_coupled_augmentation_packet_set.schema.json`

```bash
adds-frontier validate-coupled-augmentation
adds-frontier summarize-coupled-augmentation
adds-frontier validate-private-coupled-augmentation  # maintainer environment only
```

### Counterbalanced three-arm placebo control

The source-ID control tests nuisance invariance but does not match the candidate reveal's
structural magnitude. A second control layer therefore creates one content-null reveal per task
and compiles ten private triplets containing canonical, targeted-reveal, and placebo-reveal arms.
Arm roles are sealed separately from reviewer packets.

Candidate and placebo both add exactly one independent `source` node available at stage 4, append
that node to stages 4-6, and preserve every other node, edge, stage field, task field, and budget.
The placebo uses a fixed neutral vocabulary with the same whitespace-token count as its candidate.
Role placement follows a deterministic Latin square: each role appears `3/3/4` times across
`arm_a`, `arm_b`, and `arm_c`, so maximum positional imbalance is one.

These checks close the field-structure and coarse length confounds only. They do not establish
tokenizer-level matching, syntactic equivalence, semantic irrelevance, candidate coupling, or
candidate-versus-placebo contrast identifiability. The public state therefore sets
`three_arm_design_ready=true` and `structural_confound_control_ready=true`, while keeping
`lexical_confound_control_ready=false`, all coupling/invariance/contrast labels at zero, and all
scientific-establishment fields false.

- Public summary: `rl_env/specs/frontier_coupled_placebo_summary.json`
- Public schema: `rl_env/specs/frontier_coupled_placebo_summary.schema.json`
- Private schemas: `rl_env/specs/frontier_private_coupled_placebo_packet_set.schema.json` and
  `rl_env/specs/frontier_private_coupled_placebo_key_set.schema.json`

```bash
adds-frontier validate-coupled-placebo
adds-frontier summarize-coupled-placebo
adds-frontier validate-private-coupled-placebo  # maintainer environment only
```

### Tokenizer-aware five-arm placebo control

Whitespace matching leaves model-specific token length uncontrolled. The next layer therefore
preserves the three-arm baseline and compiles a separate five-arm packet for each task: canonical,
targeted reveal, and transport-, schema-, and audit-vocabulary placebo reveals. Every placebo adds
the same independent `source` field structure at stage 4 and exposes it through stages 4-6.

The compiler freezes `tiktoken 0.14.0`, `cl100k_base`, and `o200k_base`. It publishes each official
encoding asset URL and SHA-256 plus a normalized fingerprint over mergeable ranks, special tokens,
and the tokenizer regex. For every placebo it performs 512 deterministic vocabulary searches while
preserving whitespace count. Trial zero is frozen as the baseline; a later exact-count proposal is
eligible only if none of its four encoding-by-profile components regresses, and selection minimizes
total token byte-length/rank-decile L1 distance with a deterministic tie break. Across 30 placebo
arms, all 60 encoding-specific token-count comparisons match. Five-role cyclic allocation places
every role exactly twice in each of `arm_a` through `arm_e`, producing zero positional imbalance.

The selected profiles reduce aggregate L1 distance from the trial-zero baseline of `1908` to
`1454`, a reduction of `454` (23.8%). All `30/30` placebos improve strictly; all `120/120`
encoding-by-profile components are non-regressing, with `102/120` strict improvements; and all
`60/60` encoding-level combined comparisons are non-regressing. These are deterministic in-search
optimization diagnostics. They are not held-out results, external validation, or evidence that the
candidate and placebo token distributions are equivalent.

After selection is complete, a separate evaluation-only path loads frozen `r50k_base` and
`p50k_base` assets with independent source hashes and vocabulary fingerprints. These encodings are
never passed to the search function. The diagnostic is explicitly post-selection and not
preregistered. Across 60 evaluation-only encoding comparisons, aggregate profile L1 falls from
`2166` to `1940`, a reduction of `226` (10.4%). Both tokenizer-level aggregates and all three
vocabulary-family aggregates improve. At the finer level, however, only `52/60` encoding
comparisons are non-regressing and `44/60` improve strictly. Only `26/30` placebos avoid regression
across both encodings and `22/30` improve strictly across both; four placebos regress. Component
non-regression is `98/120`, and token-count-gap non-regression is `48/60`. Exact token counts match
only `4/60` after optimization.

This mixed result is retained rather than used to retune the search. The public contract marks
aggregate improvement as observed while keeping
`heldout_robust_placebo_generalization_ready=false`,
`heldout_token_count_confound_control_ready=false`, and
`heldout_tokenizer_family_independence_established=false`. The two evaluation encodings share a
50k tokenizer family, so they are not two independent external replications.

Exact count does not imply token identity or distribution. Neither byte-length nor rank-decile
histograms match exactly in any of the 60 comparisons. The public state therefore sets
`tokenizer_count_confound_control_ready=true` and
`deterministic_distribution_optimization_ready=true`, but keeps
`tokenizer_distribution_confound_control_ready=false`, `lexical_confound_control_ready=false`,
all scientific-establishment fields false, and all reviewer/label/admission/model counts at zero.
The vocabulary families are procedural controls, not evidence that any placebo is scientifically
irrelevant.

- Public summary: `rl_env/specs/frontier_tokenizer_placebo_summary.json`
- Public schema: `rl_env/specs/frontier_tokenizer_placebo_summary.schema.json`
- Private schemas: `rl_env/specs/frontier_private_tokenizer_placebo_packet_set.schema.json` and
  `rl_env/specs/frontier_private_tokenizer_placebo_key_set.schema.json`

```bash
adds-frontier validate-tokenizer-placebo
adds-frontier summarize-tokenizer-placebo
adds-frontier validate-private-tokenizer-placebo  # maintainer environment only
```

### Independent tokenizer-family evaluation

The r50k/p50k diagnostic shares a BPE lineage with the search tokenizers. A second-stage protocol
therefore freezes two algorithmically different implementations before evaluating any private
text: `tokenizers 0.23.1` BERT WordPiece and `sentencepiece 0.2.2` T5 unigram. Model repositories,
40-character revisions, Apache-2.0 licenses, official asset URLs, byte sizes, and SHA-256 values are
fixed in the public protocol. Local evaluation verifies each asset and package version before
tokenization and adds no CLS, SEP, BOS, EOS, or padding tokens.

The profile combines an eight-bin token-piece UTF-8 byte-length histogram with a three-class
word-start/continuation/unknown histogram. The protocol, profile, denominator, gate order, and
failure policy were locally sealed before this evaluation. This is not a public preregistration or
an externally timestamped seal. Evaluation text was not accessed before the local seal, the
upstream cl100k/o200k selection was already fixed, and independent-family results cannot retune
that selection or revise thresholds.

Across 60 tokenizer/placebo comparisons, aggregate profile L1 decreases from `1720` to `1532`, a
reduction of `188` (10.9%). Both tokenizer aggregates and all three vocabulary-family aggregates
improve. These aggregate results do not satisfy the strict gate: profile non-regression is
`51/60`, component non-regression is `94/120`, only `23/30` placebos avoid profile regression, and
seven placebos regress. Token-count-gap non-regression is `44/60`, with only `1/60` exact optimized
token-count matches. Unknown-token totals are zero for candidate, baseline, and optimized text.

The failures are retained without retuning. The public summary therefore sets aggregate
improvement to true while keeping independent-family profile generalization, token-count confound
control, and overall independent-family control false. It does not establish token-distribution
equivalence, semantic placebo invariance, scientific irrelevance, model behavior, or benchmark
performance. Private text and per-placebo failure locations remain outside Git and Hugging Face;
the public report contains aggregate counts, frozen provenance, commitments, and nonclaims only.

- Public protocol and schema:
  `rl_env/specs/frontier_tokenizer_independent_evaluation_protocol.json` and adjacent schema
- Public summary and schema:
  `rl_env/specs/frontier_tokenizer_independent_evaluation_summary.json` and adjacent schema
- Private report contract:
  `rl_env/specs/frontier_private_tokenizer_independent_evaluation_report.schema.json`

```bash
adds-frontier validate-tokenizer-independent-evaluation
adds-frontier summarize-tokenizer-independent-evaluation
adds-frontier validate-private-tokenizer-independent-evaluation  # maintainer environment only
```

### Independent author-oracle challenge

Semantic pair consistency and canonical replay cannot show that the author oracle itself is
scientifically correct. A separate challenge protocol therefore projects each of the ten canonical
calibration tasks into a private single-task packet. Packets retain the staged task evidence needed
for expert solving but omit slot/task mappings, commitment nonces, authoring sources, author-oracle
stage expectations, mutation expectations, and all semantic-review material. A sealed private key
binds each opaque packet to the canonical task and author oracle.

Exactly two unique, conflict-free, independence-attested challengers must answer all six stages.
Responses bind packet/task commitments and include factorized actions, witnesses, blockers, and
stage-level abstention. Access to the author oracle, semantic-review artifacts, or authoring sources
invalidates a response. The sealed mapping may open only after two valid responses exist and those
responses are compared with each other.

The frozen comparison routes are:

1. any challenger abstention -> human adjudication without oracle opening;
2. any challenger action or support disagreement -> human adjudication without oracle opening;
3. exact challenger agreement with any of 30 author-oracle component mismatches -> author-oracle
   disagreement adjudication; and
4. exact challenger agreement plus `30/30` author-oracle agreement ->
   `oracle_convergence_candidate`.

The fourth route is deliberately non-promotional. It does not establish source truth, scientific
correctness, expert-solve gate completion, or board admission, and it cannot exclude shared error
among both challengers and the author. All ten private records are currently `unassigned`; assignment,
response, convergence-candidate, and adjudication counts are zero. The public readiness artifact
contains commitments and aggregate zero-state only.

- Public summary: `rl_env/specs/frontier_oracle_challenge_readiness_summary.json`
- Public summary schema: `rl_env/specs/frontier_oracle_challenge_readiness_summary.schema.json`
- Private contracts: adjacent `frontier_private_oracle_challenge_*` packet, key, response,
  comparison, and ledger schemas

```bash
adds-frontier validate-oracle-challenge
adds-frontier summarize-oracle-challenge
adds-frontier validate-private-oracle-challenge  # maintainer environment only
```

## Counterfactual design

Each canonical task must have at least five preregistered mutations. Mutations
fall into three classes:

- **critical flips**: change one authorization-relevant fact and require a
  different disposition, action, flag, witness, or blocker;
- **nuisance invariances**: alter names, order, formatting, or equivalent units
  without changing the valid decision; and
- **evidence ladders**: add one valid independent evidence item and test whether
  the corresponding blocker, but no unrelated blocker, is removed.

Counterfactuals must remain internally coherent. A mutation generator is not an
authority for scientific correctness; canonical tasks and mutation semantics
require independent review before model scoring.

## Pilot and scale-up

The first exit gate is 40 canonical tasks: eight per task family, each with at
least five mutations. The full benchmark requires at least 300 independent base
tasks and 1,500 diagnostic cases, with held-out separation by program, disease,
and time.

Primary and partial results must be paired at the base-program level. Confidence
intervals and hypothesis tests must respect program-level clustering rather than
treating mutations or repeated model calls as independent scientific tasks.

Required partial metrics are valid-trajectory survival, first critical failure,
retrieval recall, witness/blocker exactness, unauthorized-commit rate,
contradiction recovery, the risk-coverage-cost surface, and normalized progress
toward a valid state.

## Threat boundary

The protocol explicitly covers benchmark contamination, post-cutoff leakage,
identity rebinding, derivative-source double counting, endpoint/population
mismatch, prompt injection in retrieved text, abstention-only safety gains,
automation bias, and author overfitting.

Hashes establish byte and artifact identity. They do not establish source truth,
scientific validity, or independence. Evidence independence is defined on an
underlying lineage graph, not by distinct URLs, source ids, or file hashes alone.

## Current boundary

The repository now contains the research protocol, frozen vocabulary, full-pass
aggregator, strict validators, CLI, schemas, one design seed per family, and five
public development task/oracle fixtures. It does not yet contain a real
independently curated frontier board, expert or structured-oracle baseline,
frontier-model result, external disease holdout, or human workflow study.

The next scientific milestone is to curate the 40-task baseline-blind pilot board
and its reviewed evidence-lineage graphs before running any frontier model.

## Validate

```bash
adds-frontier validate-protocol
adds-frontier summarize-protocol
adds-frontier validate-seeds
adds-frontier summarize-seeds
adds-frontier validate-development
adds-frontier summarize-development
adds-frontier validate-board
adds-frontier summarize-board
```
