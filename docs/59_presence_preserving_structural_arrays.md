# Presence-Preserving ClinicalTrials.gov Structural Arrays

## Result

The v1 registry inventory normalizes missing structural arrays to empty tuples. That is useful for
bounded pair enumeration, but it cannot distinguish a key source-level question: did a trial omit
an array, publish it as `null`, publish an empty array, or publish one or more records?

This increment adds an **additive, source-bound sidecar**. It does not mutate the v1 inventory,
candidate graph, diagnostic report, or structural decomposition. Before recording any presence
state, the compiler reconstructs the v1 inventory spec and requires the exact inventory to replay
from the exact source bundle. The public harmonization report then binds the candidate packet,
prior structure report, inventories, source content hashes, and sidecar fingerprints.

## Preserved Structure

Every source array consumed by the v1 posted-outcome parser is represented at its exact JSON
pointer. Each record retains its outcome and parent hashes, state, item count, and source-value
hash, but not the source array value.

| Role | ClinicalTrials.gov key | Derived v1 field |
| --- | --- | --- |
| Outcome groups | `groups` | `group_count` |
| Outcome denominators | `denoms` | `denominator_count` |
| Outcome denominator counts | `denoms[*].counts` | `denominator_count` |
| Outcome classes | `classes` | `class_count` |
| Class denominators | `classes[*].denoms` | `denominator_count` |
| Class denominator counts | `classes[*].denoms[*].counts` | `denominator_count` |
| Class categories | `classes[*].categories` | `category_count` |
| Category measurements | `classes[*].categories[*].measurements` | `measurement_count` |
| Outcome analyses | `analyses` | `analysis_count` |
| Analysis group ids | `analyses[*].groupIds` | `analysis_group_id_sets` |

The four states are `absent`, `present_null`, `present_empty`, and `present_nonempty`. Synthetic
controls exercise all four, including the nested-empty case where v1 represents both
`groupIds: null` and `groupIds: []` as `((),)`. Zero/empty detection is recursive so this case is
now explicitly routed to source-presence resolution.

## Exact Public Executions

The exact source snapshots remain outside Git. Public outputs contain aggregate profiles and
cryptographic bindings only; per-pointer sidecars are replay intermediates and are not published.

| Cohort | Trials | Endpoints | Cross-trial pairs | Sidecar records | Legacy non-identifiable field-pairs | Resolved |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| RA olokizumab MTX-IR | NCT02760368, NCT02760407 | 12 | 35 | 50 + 75 | 0 | 0 |
| UC ozanimod | NCT01647516, NCT02435992 | 21 | 110 | 169 + 90 | 192 | 192 |

RA already had positive values for all seven structural fields, so the v1 structure report's
source-presence identifiability was confirmed without changing any pair partition.

In UC, 96 of 110 pairs for `analysis_count` and the same 96 pairs for
`analysis_group_id_sets` contained at least one zero/empty value. Exact-source replay showed that
all 192 field-pairs involved an **absent `analyses` array**, not an observed empty or null array.
For each field, 27 pairs had the same zero-cause signature and 69 had different signatures because
one trial endpoint had analyses while the other did not. This resolves representation provenance;
it does not establish endpoint or estimand equivalence.

Exact report fingerprints:

- RA: `6aefcc37335edfffeb9e56bab65f3553a9ed556a61297bd830f4208089434390`
- UC: `b616abe93c94d76d0b2be0dd592416993f1e6ccdbc1da42dc5cc5b9b1398c4fc`

Exact spec/report file SHA-256 values:

- RA: `c08d42d360eb43c1da4b61df433d2c467c5ac3db9ec003c6df7a07c3b7cc209b` /
  `48b97b5c393fa57a2409bdc194f3c2d4d4186e812ed201ab1fe0efa82c00f7ee`
- UC: `08c6009088df8b5f0e3898c8cb1cb55d7154fc6e39d009bbc2f869f75dc12b74` /
  `ac5adedc621c0ab7c88d97337d96dc772753f27dc0c9dfabec4ff41cc3f67524`

## Replay

The cohort audit scripts replay inventory, candidate, diagnostic, structure, sidecar, and aggregate
presence resolution in one path:

```bash
PYTHONPATH=. python scripts/audit/compile_olokizumab_mtx_ir_harmonization_diagnostic.py \
  --nct02760368-source /path/to/NCT02760368.json \
  --nct02760407-source /path/to/NCT02760407.json \
  --spec-output /tmp/ra-diagnostic-spec.json \
  --report-output /tmp/ra-diagnostic-report.json \
  --presence-spec-output /tmp/ra-presence-spec.json \
  --presence-report-output /tmp/ra-presence-report.json
```

The generic CLI exposes the two additive stages:

```bash
adds-pinned-ingestion compile-clinicaltrials-gov-structural-presence \
  --spec sidecar-spec.json --bundle source-bundle --inventory inventory.json \
  --output sidecar.json

adds-pinned-ingestion resolve-clinicaltrials-gov-harmonization-presence \
  --spec presence-spec.json --candidate-packet candidates.json \
  --structure-report structure.json --sidecar trial-a.json --sidecar trial-b.json \
  --output presence-report.json
```

Both commands use strict duplicate-safe readers, bounded input/work checks, integrity envelopes,
and atomic output writes. JSON Schemas and synthetic examples are in `rl_env/specs/`.

## Interpretation Boundary

The sidecar answers only how the exact registry snapshot represented structural arrays. It does
not retain endpoint titles or array values, approve or exclude endpoint pairs, infer endpoint
identity, identify an estimand, establish population or safety comparability, pool effects, rank
trials, synthesize benefit-risk, or choose a treatment.

The next scientific priority is to use these now-identifiable representation causes as explicit
inputs to a preregistered endpoint/estimand review protocol. Missing analyses should become a typed
review blocker, not a numerical proxy for incompatibility and not an automatic exclusion rule.
