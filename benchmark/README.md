# ctdbench

A small, pip-installable runner and scorer for the **clinical-trial decision benchmark** — a construct-valid,
no-human, calibrated-abstention benchmark that frames trial evaluation as a *decision* (`advance` / `stop` /
`verify`, or abstain) rather than an outcome probability.

Dataset: https://huggingface.co/datasets/jang1563/clinical-trial-decision-benchmark

## Install

```bash
pip install ctdbench            # scoring only, offline (needs pyarrow)
pip install 'ctdbench[hf]'      # + load splits from the Hugging Face Hub
```

## Use

```python
from ctdbench import load_gold, evaluate

gold  = load_gold(split="test")                    # {nct_id: "advance"|"stop"|"verify"}
preds = {nct: my_agent(nct) for nct in gold}       # your model's decision; omit a key to abstain
print(evaluate(preds, gold))
# {'n_gold': ..., 'n_scored': ..., 'coverage': ...,
#  'balanced_accuracy': ..., 'macro_f1': ..., 'per_class_f1': {...},
#  'trivial_floor_balanced_accuracy': ...}
```

`balanced_accuracy` (macro-recall) is the headline metric — the classes are imbalanced (~60% `stop`), so a
model is only meaningful once it clears `trivial_floor_balanced_accuracy` (the always-one-class floor).
Abstention is first-class: decline a trial by omitting it, and `coverage` reports how much you acted on.

For a selective policy that emits confidences, `risk_coverage(preds, gold, confidences)` returns the
risk–coverage curve.

## CLI

```bash
ctdbench info --split test
ctdbench evaluate --predictions my_preds.json --split test
# offline, against a local Parquet dir:
ctdbench --local-dir ./data evaluate --predictions my_preds.json --split test
```

## Scope

The scorer is model-agnostic — it takes your decisions and the gold labels and reports the metrics. Labels are
weak-supervision, source-derived (no human annotation at scale); see the dataset card for the construct-validity
check, the calibrated-abstention analysis, and the honest limitations.
