# Cross-Trial Harmonization Difficulty Diagnostics

Status: implemented, tested, and executed on two exact public ClinicalTrials.gov snapshots

## Research question

Can an end-to-end drug-discovery agent expose the full endpoint and safety harmonization workload
before semantic review, without publishing endpoint text, pair identities, event terms, or an
unsupported comparability decision?

The diagnostic consumes the complete cross-trial candidate graph described in
`docs/55_cross_trial_harmonization_candidates.md`. It aggregates every pair into overlapping review
routes and mutually exclusive difficulty signatures. It never selects or excludes a pair. Every
pair retains `semantic_endpoint_review_required`, including mechanically exact pairs.

## Public-source execution

The exact run used the latest records retrieved on 2026-08-25 for
[NCT02760368](https://clinicaltrials.gov/study/NCT02760368?tab=results) and
[NCT02760407](https://clinicaltrials.gov/study/NCT02760407?tab=results). Both API records declared
`versionHolder=2026-08-25`. Raw JSON, source bundles, inventory packets, and the pair-level
candidate packet remain external. The public artifacts contain only NCT IDs, hashes, structural
counts, fixed limitations, and aggregate diagnostics.

| Trial | Source SHA-256 | Inventory SHA-256 | Protocol outcomes | Posted outcomes | Protocol-to-posted exact lexical links | Safety records | Group-level safety statistics |
|---|---|---|---:|---:|---:|---:|---:|
| `NCT02760368` | `72cd2ce3bb7a7b1dbd9a115b24e273959571a52187759528d8b05005a9dd299b` | `8efb7b7d753d67d682cdf69fed755cb522730ccd56c0b26b8d5f6bc5813eebad` | 5 | 5 | 5 | 27 | 81 |
| `NCT02760407` | `854689f2a761cd428f05597b71594b28a7fa073db06991586aa560a6b4cf1a57` | `484a4b5238dc8a0669e66c16e06dd549b3777faf1563ff484fb3703aafab071b` | 7 | 7 | 7 | 85 | 340 |

Five by seven posted outcomes produce the complete 35-pair Cartesian graph. No pair was sampled or
discarded. The aggregate contains eight distinct blocker signatures.

## Workload result

| Overlapping review route | Pairs | Rate |
|---|---:|---:|
| Semantic endpoint review | 35 | 100.0% |
| Source-field completion | 34 | 97.1% |
| Within-trial reconciliation | 0 | 0.0% |
| Title identity | 31 | 88.6% |
| Time frame | 22 | 62.9% |
| Outcome type | 10 | 28.6% |
| Reporting status | 0 | 0.0% |
| Estimand structure | 35 | 100.0% |
| Population | 10 | 28.6% |
| Safety window | 35 | 100.0% |

All 35 pairs had at least two additional mechanical blockers beyond semantic review. Mechanical
status was `incomplete_source_fields` for 34 pairs and `mixed_mechanical_fields` for one; none had
all mechanical fields equal. The incompleteness is concentrated in dispersion type: both trials
reported it for only one cross-trial pair, while 34 pairs had at least one missing value.

| Field | Both observed | Exact among observed | Disagreement among observed | At least one missing |
|---|---:|---:|---:|---:|
| Title | 35 | 4 | 31 | 0 |
| Time frame | 35 | 13 | 22 | 0 |
| Outcome type | 35 | 25 | 10 | 0 |
| Reporting status | 35 | 35 | 0 | 0 |
| Parameter type | 35 | 25 | 10 | 0 |
| Dispersion type | 1 | 1 | 0 | 34 |
| Unit of measure | 35 | 25 | 10 | 0 |
| Population-description hash | 35 | 25 | 10 | 0 |
| Safety time frame | 35 | 0 | 35 | 0 |

Observed-field denominators are explicit: a missing value is never counted as agreement or
disagreement. Structural equality is also separate. Group count, measurement count, and analysis
group-ID sets disagreed for all 35 pairs; analysis count disagreed for 25. Those differences route
work to estimand review but do not establish that endpoints are clinically different.

## Interpretation

This result identifies a hard-agent problem that ordinary text similarity does not solve. The
agent must preserve an exhaustive graph, distinguish missingness from disagreement, retain
within-trial reconciliation provenance, treat safety windows independently, and route overlapping
review requirements without converting mechanical equality into semantic approval.

The result does **not** estimate endpoint equivalence, population exchangeability, comparative
safety, efficacy, a pooled effect, benefit-risk, model accuracy, or treatment choice. The 35 pairs
are a review universe, not 35 plausible mappings. Human semantic review was unavailable for this
run, so no endpoint family, pair approval, pair exclusion, or synthesis was produced.

## Machine contract

- Diagnostic spec: `docs/ra_olokizumab_mtx_ir_harmonization_diagnostic_spec.json`
- Diagnostic report: `docs/ra_olokizumab_mtx_ir_harmonization_diagnostic_report.json`
- Candidate packet SHA-256: `cabb2ac6c2321483072c210dbfb677acbf6dad4ddd237181ecc0846d6f7ac004`
- Diagnostic report integrity SHA-256: `6a0d2aa20eafe670d6509fc4154558c10a783d5851ff476314b2d7dc86a0b089`
- Diagnostic spec file SHA-256: `9a194ef4ab68defe5c2172bada9e18c6d520a49ff719f22bce02e932648370ea`
- Diagnostic report file SHA-256: `a195f48cb56a6dde1ca27d7e5ec703585cb9750b3f78bf75b9aba10c1ae853a2`

Strict readers reject duplicate keys, non-finite values, unknown fields, reordered code sets,
invalid denominators, non-Cartesian pair counts, route/signature inconsistencies, rebound hashes,
changed nonclaim flags, and envelope-integrity mismatch. JSON Schemas provide the matching machine
surface. The public-artifact test also rejects pair IDs, endpoint IDs, safety records, endpoint
titles, and safety-window payload fields.

For any exact candidate packet, compile the aggregate with:

```bash
adds-pinned-ingestion diagnose-clinicaltrials-gov-harmonization \
  --spec /external/review/harmonization-diagnostic.spec.json \
  --candidate-packet /external/review/harmonization.candidates.json \
  --output /external/review/harmonization-diagnostic.report.json
```

The input remains pair-level review material and should stay outside a public repository unless it
receives its own release review. The command bounds candidate-packet bytes before strict parsing
and writes the report atomically.

## Exact replay

Capture the two exact API payloads whose hashes appear above outside the repository, then run:

```bash
uv run python scripts/audit/compile_olokizumab_mtx_ir_harmonization_diagnostic.py \
  --nct02760368-source "$SOURCE_DIR/NCT02760368.json" \
  --nct02760407-source "$SOURCE_DIR/NCT02760407.json" \
  --retrieved-at 2026-08-25T17:39:58.865108+00:00 \
  --spec-output /tmp/olokizumab-harmonization.spec.json \
  --report-output /tmp/olokizumab-harmonization.report.json
```

The script verifies both source hashes, recompiles both inventories and the complete candidate
graph, validates every layer, and reproduces the public spec/report byte for byte. A later mutable
registry snapshot is a new evidence version and must not silently replace this run.
