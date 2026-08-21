# Olokizumab MTX-IR Week-12 ACR20 Risk-of-Bias Assessment

## Research question

Can the remaining `risk_of_bias_not_assessed` blocker in the same-stratum olokizumab MTX-IR
replication be narrowed using exact public trial sources without implying pooling, transportability,
or a clinical recommendation?

This execution assesses the Week-12 ACR20 result for
[NCT02760407](https://clinicaltrials.gov/study/NCT02760407?tab=results) and
[NCT02760368](https://clinicaltrials.gov/study/NCT02760368?tab=results). It is a project-internal,
outcome-specific structured assessment. It is not an official Cochrane RoB 2 assessment or an
independent external review.

## Result

Both trials receive an overall `some_concerns` judgment. Outcome measurement is the only `low`
domain. The other four domains remain `some_concerns`: the public package does not expose the IWRS
sequence-generation algorithm or allocation audit, realized unblinding and complete deviation
data, observed-versus-assigned Week-12 ACR20 status by arm, or a standalone final analysis plan
verified as finalized before unblinding.

| Domain | NCT02760407 | NCT02760368 | Source-bound basis |
|---|---|---|---|
| Randomization process | `some_concerns` | `some_concerns` | Randomized parallel design and automated IWRS assignment by blinded staff are documented; sequence-generation and audit details are absent. |
| Deviations from intended interventions | `some_concerns` | `some_concerns` | Participant/investigator masking and restricted code access were planned; realized unblinding and complete deviation counts are unavailable. |
| Missing outcome data | `some_concerns` | `some_concerns` | Analysis denominators equal STARTED counts and treatment-failure rules were prespecified, but public aggregates do not separate observed outcomes from assigned non-response or imputed values by arm. |
| Measurement of the outcome | `low` | `low` | Posted ACR20 definitions match the prespecified composite; independent blinded joint assessment is documented. |
| Selection of the reported result | `some_concerns` | `some_concerns` | The dated registry-labeled protocol/SAP artifact predates completion and prespecifies the analysis, but the reviewed PDF is a clinical protocol/local amendment and a standalone final pre-unblinding SAP was not verified. |
| Overall | `some_concerns` | `some_concerns` | The most concerning supported domain determines the conservative project-internal result. |

Here, `low` means lower concern under this bounded public-source assessment. It does not attest to
complete access to the clinical study report, participant-level data, monitoring records, or an
independent risk-of-bias adjudication.

## Identity, denominator, and document checks

| Trial | Selected arms | STARTED | Week-12 ACR20 analysis denominator | Reviewed PDF | Primary completion | Executable checks |
|---|---|---:|---:|---|---|---|
| `NCT02760407` | OKZ 64 mg q4w + MTX vs placebo + MTX | 479 vs 243 | 479 vs 243 | 2018-05-28; 173 pages | 2019-08-02 | Arm/result pair, endpoint 0, date, pages, and excerpts verified |
| `NCT02760368` | OKZ 64 mg q4w + MTX vs placebo + MTX | 142 vs 143 | 142 vs 143 | 2018-03-30; 181 pages | 2018-08, month precision | Module-specific arm titles, endpoint 0, date, pages, and excerpts verified |

The denominator check is exact for the selected registry result groups, but it establishes the ITT
analysis population rather than complete observed outcome availability. It does not reconstruct
participant-level missingness, distinguish observed values from assigned or imputed outcomes, or
verify every post-randomization event. PDF citations are parsed and checked against page count,
title-page date, cited page, and normalized source excerpt; source bytes remain external.

## Transport blocker delta

The linked same-stratum transport report contained five blockers. This follow-on resolves exactly
one:

- Resolved: `risk_of_bias_not_assessed`
- Remaining: `target_population_not_declared`
- Remaining: `aggregate_registry_results_only`
- Remaining: `individual_level_covariates_unavailable`
- Remaining: `transport_model_not_preregistered`

No pooled effect, cross-trial contrast, transport estimate, safety conclusion, or treatment
recommendation is emitted. The prior transport report remains an immutable v1 artifact with its
historical blocker ledger; the new report records the exact follow-on delta.

## Provenance

| Artifact | SHA-256 |
|---|---|
| Linked transport report | `3102fa78eec99959e0a2b5025ec5232b7abb2e51c81065fd98be73ec36e7b2cd` |
| Reviewed risk-of-bias spec | `f9f0bd3a6e67f866415d5df71d581ee9fd55e161211321be4605ac7cfae90aed` |
| Risk-of-bias report | `d73c5c14ba347f96cecaf9b8b9362b01d1ff210d3d179677192e17f046e5b502` |
| NCT02760407 registry JSON | `62415b71d08c8d5ccbe0b03be45bad4ad8bd734d43de461be52278314fbb59d8` |
| NCT02760407 protocol/SAP PDF | `1b9287681119f071323663b32533fa5eff0195da50bece3fb5e057d71b11cd35` |
| NCT02760368 registry JSON | `7d0f38ee584e2af66cc7b4ebec8d2cc8b86327183a887eba6c5ce1ff96a2d1e7` |
| NCT02760368 protocol/SAP PDF | `f44519001749ffe648c79e6d2e66474e9f2779025b2085726def415ef899a2e7` |

The reviewed machine contract is
`docs/ra_olokizumab_mtx_ir_risk_of_bias_spec.json`; the compiled result is
`docs/ra_olokizumab_mtx_ir_risk_of_bias_report.json`. Each domain cites both an exact registry JSON
field and an exact registry-labeled protocol/SAP PDF hash, page, section, and excerpt. Trial records
also preserve separate participant-flow and outcome-result arm titles so source wording differences
cannot silently rebind an arm. The public JSON files contain no local paths or raw source payloads.

## Replay

After capturing the two exact registry JSON payloads and registry-linked protocol/SAP PDFs, replay
with:

```bash
uv run python scripts/audit/compile_olokizumab_mtx_ir_risk_of_bias.py \
  --nct02760407-registry "$SOURCE_DIR/NCT02760407/payload.bin" \
  --nct02760407-protocol-sap "$SOURCE_DIR/NCT02760407/Prot_SAP_000.pdf" \
  --nct02760368-registry "$SOURCE_DIR/NCT02760368/payload.bin" \
  --nct02760368-protocol-sap "$SOURCE_DIR/NCT02760368/Prot_SAP_000.pdf" \
  --reviewed-at 2026-08-21T16:45:00+00:00 \
  --spec-output docs/ra_olokizumab_mtx_ir_risk_of_bias_spec.json \
  --report-output docs/ra_olokizumab_mtx_ir_risk_of_bias_report.json
```

Re-execution fails closed if a registry field, PDF byte sequence, module-specific arm binding,
endpoint pointer/title, analysis pair, denominator, PDF page/date/excerpt, protocol chronology,
linked transport report, spec, or report integrity hash changes.
