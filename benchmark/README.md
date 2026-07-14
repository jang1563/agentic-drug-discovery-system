# ctdbench

A small, pip-installable runner and scorer for the **clinical-trial decision benchmark** — a construct-audited,
source-derived-label benchmark with abstention analysis that frames trial evaluation as a *decision* (`advance` / `stop` /
`verify`, or abstain) rather than an outcome probability.

Dataset: https://huggingface.co/datasets/jang1563/clinical-trial-decision-benchmark

## Install

From a clone of this repository:

```bash
python3 -m pip install ./benchmark
python3 -m pip install './benchmark[hf]'  # adds Hugging Face Hub loading
```

Or install the GitHub subdirectory directly:

```bash
python3 -m pip install \
  'ctdbench[hf] @ git+https://github.com/jang1563/agentic-drug-discovery-system.git#subdirectory=benchmark'
```

`ctdbench` is not currently published on PyPI; a bare `pip install ctdbench`
is therefore not a supported installation path.

## Use

```python
from ctdbench import load_gold, evaluate

gold  = load_gold(split="test")                    # pinned Hub revision; see DEFAULT_REVISION
preds = {nct: my_agent(nct) for nct in gold}       # your model's decision; omit a key to abstain
print(evaluate(preds, gold))
# {'n_gold': ..., 'n_scored': ..., 'coverage': ...,
#  'balanced_accuracy': ..., 'conditional_balanced_accuracy': ...,
#  'coverage_adjusted_balanced_accuracy': ..., 'per_class_coverage': {...},
#  'trivial_floor_balanced_accuracy': ...}
```

`balanced_accuracy` averages recall over every class present in the full gold
split. If a model abstains on an entire class, that class receives recall 0
instead of disappearing from the average. The scorer also reports:

- `conditional_balanced_accuracy`: performance over classes represented in the
  acted subset; interpret only beside coverage.
- `coverage_adjusted_balanced_accuracy`: class-balanced recall with abstained
  gold rows counted as misses.
- `per_class_coverage`: the acted fraction within each class.

The classes are imbalanced (~60% `stop`), so compare the all-class balanced
score with `trivial_floor_balanced_accuracy`. Unsupported decision labels fail
closed instead of being silently scored as arbitrary errors.

For a selective policy that emits confidences, `risk_coverage(preds, gold, confidences)` returns the
risk–coverage curve.

## CLI

```bash
ctdbench info --split test
ctdbench evaluate --predictions my_preds.json --split test
# offline, against a local Parquet dir:
ctdbench --local-dir ./data evaluate --predictions my_preds.json --split test
```

Hub downloads default to the immutable dataset commit exported as
`ctdbench.DEFAULT_REVISION`. Pass `--revision <commit-or-tag>` before the
subcommand, or `revision=` to `load_records` / `load_gold`, to evaluate another
explicit dataset revision. `--local-dir` remains the offline path.

## Scope

The scorer is model-agnostic — it takes your decisions and the gold labels and reports the metrics. Labels are
weak-supervision, source-derived (no human annotation at scale); see the dataset card for the construct-validity
check, retrospective abstention analysis, and honest limitations.

## Test

From the repository root after installation:

```bash
python3 -m pytest -q benchmark/tests
```
