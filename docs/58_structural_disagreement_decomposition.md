# Structural Disagreement Decomposition

Status: exact public-source execution completed on 2026-08-25

Scope: payload-free decomposition of the existing RA olokizumab and UC ozanimod complete
cross-trial endpoint graphs

## Research question

When a structural field disagrees for every cross-trial endpoint pair, is the disagreement a
trial-wide design property or does it vary among endpoints inside a trial?

The distinction matters because a saturated pairwise rate can be produced by one constant arm
layout difference. Such a rate does not by itself show that individual endpoints are structurally
heterogeneous. The compiler therefore refines each existing structural exact/disagreement count;
it does not replace or discount the original diagnostic.

## Preregistered mechanical partition

For each of seven structural fields, every complete-graph pair receives exactly one label:

1. `exact`: the two endpoint values are identical;
2. `trial_global_disagreement`: the values differ and that field is constant across every posted
   endpoint within both source trials; or
3. `endpoint_local_disagreement`: the values differ and the field varies within at least one
   source trial.

Pair-level categories are then mutually exclusive: all fields exact, trial-global disagreement
only, or at least one endpoint-local disagreement. The spec binds both the exact candidate packet
and the prior diagnostic report by SHA-256. Compilation fails unless each new exact count equals
the prior exact count and the two disagreement causes sum to the prior disagreement count.

No raw structural values, endpoint titles, endpoint IDs, pair IDs, safety terms, or source pointers
are retained in the public report. Trial-level profiles retain only endpoint count, unique-value
count, zero-or-empty count, and a constant/not-constant flag for each field.

## Exact result

The two cohorts contain 33 posted endpoints and 145 complete-graph pairs in total. Denominators
remain cohort-specific; no cross-disease pooling or weighting is performed.

| Structural field | RA exact | RA trial-global | RA endpoint-local | UC exact | UC trial-global | UC endpoint-local |
|---|---:|---:|---:|---:|---:|---:|
| Group count | 0/35 | 35/35 | 0/35 | 0/110 | 0/110 | 110/110 |
| Denominator count | 35/35 | 0/35 | 0/35 | 110/110 | 0/110 | 0/110 |
| Class count | 35/35 | 0/35 | 0/35 | 77/110 | 0/110 | 33/110 |
| Category count | 35/35 | 0/35 | 0/35 | 77/110 | 0/110 | 33/110 |
| Measurement count | 0/35 | 35/35 | 0/35 | 77/110 | 0/110 | 33/110 |
| Analysis count | 10/35 | 0/35 | 25/35 | 27/110 | 0/110 | 83/110 |
| Analysis group-ID sets | 0/35 | 0/35 | 35/35 | 27/110 | 0/110 | 83/110 |

Every pair in both cohorts has at least one endpoint-local structural disagreement. This does not
mean every disagreeing field is endpoint-local. In RA, `group_count` and `measurement_count` are
constant within each trial and differ only between trials, while `analysis_count` and
`analysis_group_id_sets` vary within at least one trial. In UC, six of seven fields have some
endpoint-local disagreement; only `denominator_count` is exact for all 110 pairs.

## Main finding

`group_count` disagreement was 100% in both cohorts in the preceding robustness report, but its
cause is not robust:

- RA: 35/35 disagreements are trial-global.
- UC: 110/110 disagreements are endpoint-local.

Thus identical saturated route prevalence can conceal different data-generating structure. A
model or policy evaluated only on aggregate blocker rates could appear stable across diseases
while relying on a shortcut tied to trial architecture. Field-specific cause decomposition is
therefore required before using route prevalence as evidence of endpoint-level difficulty or
cross-disease robustness.

The result also prevents an attractive but invalid optimization: trial-global disagreements are
not automatically discounted. A trial-wide difference can still be clinically decisive for an
estimand. The label only identifies where variation occurs.

## Source-presence limit

The v1 candidate representation converts optional structural arrays to empty tuples before this
stage. Positive counts mechanically establish that the source array was present and nonempty, but
the explicit presence provenance is not retained. A zero count or empty analysis-group set cannot
distinguish:

- an absent source field;
- a present but empty source array; or
- a genuinely zero-sized reported structure.

Only pairs involving at least one zero/empty value are therefore marked
`source_presence_non_identifiable`, and the report separately fixes
`source_presence_provenance_retained=false`. RA has no such pair in the seven structural fields.
UC has 96/110 non-identifiable pairs for both `analysis_count` and
`analysis_group_id_sets`; its other five structural fields have none. The report never calls zero
or empty values missing. These are observability diagnostics, not missingness estimates.

## What is established

The implementation provides a deterministic, integrity-bound, payload-free refinement of all
seven structural diagnostics for complete cross-trial candidate graphs. It supports zero-endpoint
trials, canonical multi-trial order, strict JSON duplicate-key and non-finite-value rejection,
bounded work, exact report replay, schema validation, and atomic CLI output. Synthetic controls
separate trial-global-only pairs from endpoint-local pairs; public artifact tests bind both RA and
UC results to exact hashes.

The result does not establish endpoint identity, semantic or estimand equivalence, population
exchangeability, clinical comparability, efficacy, comparative safety, benefit-risk, regulatory
readiness, or treatment choice. It is a causal-location diagnostic for representation structure,
not an adjudication of whether a disagreement matters clinically.

## Next research priority

The next implementation priority is a presence-preserving inventory/candidate contract that
retains `absent`, `present_empty`, and `present_nonempty` separately for every structural array.
That upgrade should be additive and versioned, with a migration test proving that current v1
artifacts remain replayable. The decomposition can then separate source-presence disagreement from
reported-value disagreement instead of marking it non-identifiable.

After that contract exists, add a third disease cohort selected before inspecting pair outcomes to
stress a different trial architecture. The preregistered test should ask whether the RA/UC cause
shift repeats, rather than merely whether another route reaches 100%.

## Machine contract and replay

- RA structure spec: `docs/ra_olokizumab_mtx_ir_structure_spec.json`
- RA structure report: `docs/ra_olokizumab_mtx_ir_structure_report.json`
- RA candidate packet SHA-256: `cabb2ac6c2321483072c210dbfb677acbf6dad4ddd237181ecc0846d6f7ac004`
- RA report integrity SHA-256: `7f6a071ffc4e83f46b0f6d1d7cf237a3f22f3a39defa355f594e6dd99e910169`
- RA spec/report file SHA-256: `9d3d6d1ff6f8b9acb39c690f871352fc39a09563b3383c7b69b6db0b3ee67358` / `5ccc691093b7b05c347ce1a092a6947202f9cc0f4e024d2b48e480ccdee9db62`
- UC structure spec: `docs/uc_ozanimod_structure_spec.json`
- UC structure report: `docs/uc_ozanimod_structure_report.json`
- UC candidate packet SHA-256: `aaefafba4d1c4bfa10c5589ceb102fe866fc5ebe89530f7fc2580aed49245b22`
- UC report integrity SHA-256: `68f64745cc9db1ce98506970834822f64f0e502e35ecacb35c944ac2b8ca5b1b`
- UC spec/report file SHA-256: `8a68c7410f9464e8a3947a73929364c5d91800df265c10391ac33a2aa0cc0504` / `8c252d7b2d7733d8aaab945bb2152c80306c8eead74883e10d6e5bb3832897d7`

Replay both diagnostics and structure reports from exact external API responses:

```bash
PYTHONPATH=. python scripts/audit/compile_olokizumab_mtx_ir_harmonization_diagnostic.py \
  --nct02760368-source /external/NCT02760368.json \
  --nct02760407-source /external/NCT02760407.json \
  --spec-output /tmp/ra-diagnostic-spec.json \
  --report-output /tmp/ra-diagnostic-report.json \
  --structure-spec-output /tmp/ra-structure-spec.json \
  --structure-report-output /tmp/ra-structure-report.json

PYTHONPATH=. python scripts/audit/compile_ozanimod_uc_harmonization_diagnostic.py \
  --nct01647516-source /external/NCT01647516.json \
  --nct02435992-source /external/NCT02435992.json \
  --spec-output /tmp/uc-diagnostic-spec.json \
  --report-output /tmp/uc-diagnostic-report.json \
  --structure-spec-output /tmp/uc-structure-spec.json \
  --structure-report-output /tmp/uc-structure-report.json
```

Compile a structure report from already materialized exact inputs:

```bash
adds-pinned-ingestion decompose-clinicaltrials-gov-harmonization-structure \
  --spec /external/structure-spec.json \
  --candidate-packet /external/candidate-packet.json \
  --diagnostic-report /external/diagnostic-report.json \
  --output /tmp/structure-report.json
```
