# Case Bank Schema v0

Date: 2026-06-28

## Purpose

This schema defines how success/failure episodes become agent-ready replay tasks. The goal is to support LLM planning, SFM specialist calls, tool/database retrieval, deterministic verification, soft verification, and dense/sparse reward scoring without live tool calls in the first benchmark version.

## Top-Level Record

```yaml
episode_id: "clinical_failure::example::000001"
schema_version: 0
created_at: "YYYY-MM-DD"
updated_at: "YYYY-MM-DD"
curation_status: "candidate | reviewed | locked | deprecated"
atlas_domain: "clinical_regulatory | target_mechanism | compound_target | admet_tox | protein_structure | cell_perturbation"
decision_stage: "target_id | hit_triage | hit_to_lead | lead_optimization | proof_of_concept | pivotal_or_regulatory | postmarket_safety"
decision_date: "YYYY-MM-DD"
evidence_cutoff_date: "YYYY-MM-DD"
```

## Entity Block

```yaml
entities:
  asset_or_candidate:
    canonical_id:
    id_system:
    names:
    synonyms:
    normalized_by:
      - source_id:
        source_version:
        mapping_confidence:
    unresolved_ambiguities:
      - note:
  target_or_mechanism:
    canonical_id:
    id_system:
    names:
    organism:
  condition_or_context:
    canonical_id:
    id_system:
    names:
    granularity:
  trial_or_program:
    nct_id:
    fda_application_id:
    sponsor:
```

## Visible Packet

The visible packet is what the agent may see or retrieve during the episode.

```yaml
visible_packet:
  packet_id:
  source_snapshots:
    - source_id:
      source_version:
      query_or_file:
      retrieved_at:
      evidence_date:
      included_before_cutoff: true
  evidence_records:
    - evidence_id:
      source_id:
      entity_refs:
      evidence_type:
      claim:
      parsed_fields:
      provenance:
      evidence_date:
      visibility: "visible | masked | decoy"
```

## Evaluator-Only Labels

Evaluator-only labels are used for scoring and must not be visible to the rollout policy.

```yaml
evaluator_labels:
  outcome_label:
  evidence_status_label:
  probativeness_label:
  gold_decision_label:
  terminal_reference:
    source_id:
    source_version:
    evidence_id:
    evidence_date:
  known_failure_modes:
    - failure_mode:
      trigger_condition:
      expected_detector:
  rationale:
    short_summary:
    reviewer_notes:
```

## Agent Interface

```yaml
agent_interface:
  allowed_actions:
    - retrieve_evidence
    - query_database
    - run_sfm
    - run_structure_tool
    - score_candidate
    - edit_candidate
    - run_verifier
    - request_more_evidence
    - stop_success
    - stop_failure
    - escalate_review
  allowed_tools:
    - tool_id:
      tool_type:
      cached_output_ref:
      cost:
  allowed_sfm_calls:
    - model_id:
      modality:
      cached_output_ref:
      cost:
  budget:
    max_steps:
    max_cost:
    max_expensive_calls:
```

## Verifier Contract

```yaml
verifiers:
  deterministic:
    - verifier_id:
      applies_to:
      pass_condition:
      fail_action: "block | repair | penalize | escalate"
  soft:
    - verifier_id:
      applies_to:
      score_range: [0, 1]
      interpretation:
      threshold_hints:
```

## Reward Contract

```yaml
reward:
  dense_components:
    - component_id:
      description:
      weight:
      evidence_required:
      visible_to_policy: false
  sparse_terminal:
    correct_decision_reward:
    incorrect_decision_penalty:
    unsafe_or_leaky_decision_penalty:
    correct_defer_reward:
  cost_model:
    step_cost:
    tool_costs:
    sfm_costs:
    human_review_cost:
```

## Baseline Outputs

```yaml
baselines:
  no_llm_rule_policy:
    decision:
    reward:
    notes:
  retrieval_only_policy:
    decision:
    reward:
    notes:
  sfm_only_policy:
    decision:
    reward:
    notes:
  llm_prompt_only_policy:
    decision:
    reward:
    notes:
```

## Review Metadata

```yaml
review:
  reviewers:
    - name_or_id:
      date:
      role:
  review_gates_passed:
    - source_version_gate
    - entity_normalization_gate
    - time_slice_gate
    - label_consistency_gate
    - reward_hacking_gate
    - baseline_sufficiency_gate
  open_issues:
    - issue:
      severity:
      owner:
```

## Minimum Lock Criteria

An episode can be marked `locked` only if:

- all source snapshots are recorded;
- entity normalization is resolved or explicitly review-flagged;
- visible evidence and evaluator-only labels are separated;
- decision date and evidence cutoff date are set;
- labels cover outcome, evidence status, probativeness, and gold decision;
- at least one deterministic verifier and one soft verifier target are specified;
- at least one no-LLM baseline is defined;
- leakage review passes.
