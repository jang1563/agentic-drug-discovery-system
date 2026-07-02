# State / Action / Observation Spec v0

## State

Required fields:

- `task_id`
- `chain_type`
- `step_index`
- `candidate_set`
- `evidence_records`
- `tool_history`
- `verifier_history`
- `uncertainty_state`
- `budget_state`
- `decision_state`

## Action

Candidate action types:

- `retrieve_evidence`
- `query_database`
- `run_sfm`
- `run_structure_tool`
- `score_candidate`
- `edit_candidate`
- `run_verifier`
- `request_more_evidence`
- `stop_success`
- `stop_failure`
- `escalate_review`

Required fields:

- `action_id`
- `action_type`
- `inputs`
- `declared_purpose`
- `expected_output_schema`
- `cost_hint`

## Observation

Required fields:

- `observation_id`
- `action_id`
- `tool_or_model`
- `raw_output_ref`
- `parsed_output`
- `deterministic_verifier_results`
- `soft_verifier_results`
- `errors`

## Trajectory Record

Required fields:

- `trajectory_id`
- `task_id`
- `policy_id`
- `initial_state`
- `steps`
- `terminal_state`
- `reward_trace`
- `outcome_label`
- `failure_modes`

