# RL Environment

This directory is for the environment abstraction that turns long-horizon discovery workflows into replayable tasks.

## Subdirectories

- `specs/`: state/action/observation/trajectory schemas.
- `rewards/`: reward decomposition and scoring functions.
- `tasks/`: task instances and benchmark splits.
- `trajectories/`: recorded or generated trajectories.
- `baselines/`: rule, retrieval, prompt-only, and verifier-ablation baselines.

## First Build Target

Start with cached-output replay. The first environment should not require live expensive model or tool calls.

Current repository scope:

- Keep schemas and reward-component definitions in Git.
- Keep concrete task instances, trajectories, evaluator labels, generated reward outputs, and case-bank-specific scripts outside Git until a release package is explicitly prepared.
