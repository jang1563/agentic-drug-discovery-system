# Episode Label Ontology v0

Date: 2026-06-28

## Purpose

The atlas should not label cases as simply success or failure. A drug discovery decision can fail clinically, fail regulatory review, be unsupported by current evidence, or be misinterpreted because the agent matched the wrong entity or context. This ontology separates those axes so dense reward and sparse terminal reward can be scored cleanly.

## Unit Of Analysis

Use a `program_decision_episode`.

Required episode key:

```text
episode_id
decision_date
decision_stage
asset_or_candidate_id
target_or_mechanism_id
condition_or_context_id
available_evidence_packet_id
evaluator_label_id
```

The same drug or target may appear in multiple episodes if the decision date, indication, modality, population, or evidence packet differs.

## Label Axes

### 1. Outcome Label

What happened in the evaluator-only or terminal reference outcome.

Allowed values:

- `approved`
- `pivotal_success`
- `phase2_success_advanced`
- `phase2_efficacy_failure`
- `phase2_safety_failure`
- `phase3_efficacy_failure`
- `phase3_safety_failure`
- `clinical_efficacy_failure_phase_unspecified`
- `clinical_safety_failure_phase_unspecified`
- `pk_pd_failure`
- `biomarker_strategy_failure`
- `endpoint_or_trial_design_failure`
- `regulatory_deficiency_or_crl`
- `business_or_strategic_discontinuation`
- `recruitment_or_operational_failure`
- `preclinical_activity_supported`
- `preclinical_activity_weak_or_conflicting`
- `admet_or_toxicity_failure`
- `structure_or_binding_supported`
- `structure_or_binding_failed`
- `cell_perturbation_supported`
- `cell_perturbation_failed_or_context_mismatched`
- `ambiguous_or_censored`

### 2. Evidence Status Label

How visible evidence relates to the claim being made.

Allowed values:

- `direct_same_asset_same_context`
- `same_asset_different_context`
- `same_target_same_context`
- `same_target_different_modality`
- `same_pathway_weak_analogy`
- `same_class_effect`
- `assay_or_model_only`
- `literature_only`
- `regulatory_only`
- `wrong_entity`
- `wrong_context`
- `unattributed`
- `future_leakage`
- `insufficient_visible_evidence`

### 3. Probativeness Label

How much the evidence should influence the decision.

Allowed values:

- `actionable_positive`
- `actionable_negative`
- `contextual_positive`
- `contextual_negative`
- `weak_positive`
- `weak_negative`
- `contradictory_mixed`
- `non_probative`
- `insufficient_evidence`
- `leakage_invalid`

This label is claim-conditional. A failed trial in the same drug and same indication may be actionable negative evidence, while a failed trial in a different population or modality may be only contextual or weak evidence.

### 4. Gold Decision Label

The preferred terminal or next action for the agent at the decision point.

Allowed values:

- `advance`
- `stop`
- `pivot_target`
- `pivot_modality`
- `pivot_population`
- `pivot_endpoint`
- `request_more_evidence`
- `defer`
- `escalate_human_review`
- `flag_invalid_or_suspicious_evidence`

The gold decision should be derived from outcome, evidence status, probativeness, uncertainty, and cost, not outcome alone.

### 5. Failure Mode Labels

Agent or evidence-processing failure types.

Allowed values:

- `drug_entity_mismatch`
- `disease_entity_mismatch`
- `target_entity_mismatch`
- `trial_entity_mismatch`
- `brand_generic_or_salt_form_mismatch`
- `dose_or_formulation_mismatch`
- `species_or_cell_context_mismatch`
- `same_name_wrong_target_or_isoform`
- `no_evidence_treated_as_negative`
- `no_evidence_treated_as_positive`
- `negative_evidence_overgeneralized`
- `mixed_evidence_overcollapsed`
- `weak_assay_overclaimed`
- `correlation_overclaimed_as_mechanism`
- `structure_confidence_overclaimed`
- `admet_risk_ignored`
- `future_leakage_used`
- `unattributed_claim`
- `unsupported_causal_jump`
- `invalid_chemistry_or_sequence`
- `proxy_reward_overoptimized`
- `premature_stop`
- `premature_advance`
- `failure_to_defer`
- `unnecessary_expensive_verification`

### 6. Difficulty / Split Labels

Allowed values:

- `name_visible`
- `name_anonymized`
- `name_scrambled_control`
- `famous_success_or_failure`
- `low_name_prior`
- `temporal_holdout`
- `target_holdout`
- `disease_holdout`
- `scaffold_holdout`
- `cell_line_holdout`
- `modality_holdout`
- `source_heldout`

These labels should be used to build splits and prevent the atlas from becoming a memorization benchmark.

## Reward Mapping

### Dense Reward Candidates

- correct entity normalization
- correct source/version use
- correct time-slice filtering
- correct evidence retrieval
- correct evidence-status label
- correct probativeness label
- valid tool call
- valid SFM output interpretation
- deterministic verifier pass
- calibrated uncertainty update
- appropriate cost control
- appropriate request for more evidence

### Sparse Terminal Reward Candidates

- correct `advance`
- correct `stop`
- correct `pivot_*`
- correct `defer`
- correct `escalate_human_review`
- correct `flag_invalid_or_suspicious_evidence`

## Labeling Rules

1. Do not infer a stop label from a failure outcome alone.
2. Do not infer an advance label from a positive model or assay result alone.
3. Always record whether the evidence was visible before the decision date.
4. If entity normalization is uncertain, label the episode as requiring review rather than forcing a gold decision.
5. If outcome and evidence are contradictory, preserve the contradiction instead of collapsing to a single binary success/failure label.
6. The policy-visible packet and evaluator-only labels must be separate artifacts.
7. Every label should have a source-backed rationale or a review flag.
