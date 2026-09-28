# ctdbench

A small, pip-installable runner, scorer, and metadata probe for the **clinical-trial decision benchmark**, a
source-derived-label benchmark with abstention that frames trial evaluation as a *decision* (`advance` / `stop`,
or abstain) rather than an outcome probability.

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

gold  = load_gold(split="test")                    # decisive advance/stop rows at the pinned revision
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

`load_gold` returns only the decisive `advance` / `stop` rows by default
(`decisive_only=True`), because `verify` has six test rows and one row moves a
three-class balanced score by several points. Pass `decisive_only=False` to keep
`verify`. A `verify` prediction on a decisive row counts as an abstention.

`load_provenance()` returns `{nct_id: {"label_source", "regulatory_signal"}}`
from the v1.1 `provenance/provenance.parquet` file (or from the v1.0 tables at
that revision). It documents how each label was derived and must not be used as
a model input: a lookup on `label_source` alone recovers the v1.0 test labels at
balanced accuracy 0.94.

For a selective policy that emits confidences, `risk_coverage(preds, gold, confidences)` returns the
risk–coverage curve.

## Metadata probe

`probe_columns(train_rows, test_rows)` fits a majority-label lookup per column on
`train` (one key per value, or per train-quartile bin for numeric and identifier
columns) and scores it on `test` with `evaluate`, reporting three-class and
decisive balanced accuracy plus a label-permutation p-value. A column that scores
far above the floor is a shortcut. The dataset card publishes the table for the
released columns; `ctdbench probe` reproduces it.

## Event-anchored labels (v2, no LLM)

`ctdbench.events` derives labels from public records only: ClinicalTrials.gov
structured primary-endpoint analyses and arm statistics (E1, E2), registry
status (E3), later higher-phase trials of the same investigational drug (E4),
Drugs@FDA first-approval events gated by label indications (E5), and a keyword
endpoint-direction rule (E6). `compose()` turns the signals into
`advance` / `stop` / `verify` / abstain with a tier (`tier1a` external event,
`tier1b` trial-internal) and a conflict flag. `scripts/build_event_labels.py`
runs the whole pipeline from the public APIs with caching; the dataset card
documents the schema and its limitations.

The released v2 gold (a draft on the dataset card) loads with `config="v2"`.
Only drug or biological interventional trials with a declared phase 1–3 carry
a decisive label; non-drug and phase 4 trials are abstained. `load_events()`
returns the per-trial signal values.

```python
from ctdbench import load_events, load_gold

gold_v2 = load_gold(split="test", config="v2")
signals = load_events()
```

```bash
ctdbench --config v2 evaluate --predictions my_preds.json --split test
```

## CLI

```bash
ctdbench info --split test
ctdbench evaluate --predictions my_preds.json --split test
ctdbench evaluate --predictions my_preds.json --split test --include-verify
ctdbench probe --permutations 2000
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
