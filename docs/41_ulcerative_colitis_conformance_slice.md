# Ulcerative Colitis Cross-Disease Conformance Slice

Date: 2026-08-20
Status: synthetic immune/inflammatory conformance; not a real clinical validation slice

## Purpose

The public project previously exercised cross-trial synthesis only with hazard-ratio,
`lower_is_better` examples. This slice tests a materially different disease and endpoint shape:
ulcerative colitis (`MONDO:0005101`), clinical remission, and ratio effects where
`higher_is_better`.

This choice is grounded in public terminology and endpoint practice. NCBI MedGen maps ulcerative
colitis to `MONDO:0005101`. FDA's draft ulcerative-colitis endpoint guidance identifies clinical
remission as a recommended primary endpoint, and public ClinicalTrials.gov records show remission
reported as a participant proportion. These sources motivate the conformance target; none supplies
measurements to the synthetic fixtures.

- [NCBI MedGen ulcerative colitis identity](https://www.ncbi.nlm.nih.gov/medgen/3532)
- [FDA ulcerative-colitis endpoint guidance](https://www.fda.gov/files/drugs/published/Ulcerative-Colitis--Clinical-Trial-Endpoints-Guidance-for-Industry.pdf)
- [ClinicalTrials.gov NCT03861143 results example](https://clinicaltrials.gov/study/NCT03861143?tab=results)

## Implemented Expansion

One shared effect contract now governs ClinicalTrials.gov extraction, reviewer-approved endpoint
mapping, non-pooled synthesis, and typed study records. Ratio effects continue into clinical
evidence tensors; percentage-point effects currently stop before the tensor:

| Effect measure | Required favorable direction | Benefit interval |
|---|---|---|
| `hazard_ratio` | `lower_is_better` | upper confidence bound below 1 |
| `odds_ratio` | `higher_is_better` | lower confidence bound above 1 |
| `risk_ratio` | `higher_is_better` | lower confidence bound above 1 |
| `risk_difference` | endpoint-declared | favorable confidence bound beyond 0 |

Registry labels such as `Hazard Ratio (HR)`, `Odds Ratio (OR)`, `Risk Ratio (RR)`, and
`Relative Risk`, `Difference in percentage`, and `Risk Difference (RD)` resolve to canonical
machine identities. Additive effects require explicit percent units and candidate-first group
order. Unsupported labels, scales, orderings, and measure/direction pairs fail closed.

## Cross-Stage Artifacts

The synthetic UC artifacts share the exact disease identity `MONDO:0005101`:

- `translational_handoff.uc.synthetic.example.json` represents two lineage-disjoint upstream
  perturbation observations and compiles only contextual evidence;
- `clinical_endpoint_mapping.uc.synthetic.example.json` binds two fictional NCT identities to the
  clinical-remission endpoint family with an odds-ratio effect contract; and
- `clinical_benefit_risk_synthesis.uc.synthetic.example.json` selects the exact mapping bindings
  for non-pooled trial-level synthesis.

All targets, interventions, NCT identifiers, measurements, sources, reviews, and outcomes in these
artifacts are synthetic. The real disease identifier does not convert them into clinical evidence.

## Executable Proof

The conformance tests exercise:

1. ClinicalTrials.gov source/job agreement for a beneficial odds ratio.
2. Registry-label canonicalization and rejection of unsupported effect types.
3. Reviewer mapping and synthesis contract round trips under the strict schemas.
4. End-to-end odds-ratio mapping, committed synthesis, and evidence-tensor compilation.
5. Rejection of odds-ratio direction reversal.
6. UC disease-identity continuity from the upstream handoff to clinical selection artifacts.

Run:

```bash
python3 -m pytest -q tests/test_cross_disease_clinical_conformance.py
python3 -m pytest -q tests/test_clinicaltrials_gov_ingestion.py
python3 -m pytest -q tests/test_clinical_benefit_risk_synthesis.py
python3 scripts/audit/validate_translational_handoff.py
```

## Claim Boundary

This slice proves that the software can represent and replay a second disease/endpoint geometry
without reversing benefit direction or dropping provenance. It does not prove that the synthetic
UC target works, that endpoints are clinically interchangeable, that odds ratios are transportable
across populations or time frames, or that any intervention is effective, safe, or acceptable.

## Next Research Decision

The provider-only follow-up is now complete for two non-sensitive public UC induction records; see
`docs/42_uc_provider_validation.md`. It tests real endpoint definitions, registry arm ordering,
induction phase identity, source capture, and uncertain-versus-beneficial gating while preserving
raw bytes and reviewer jobs outside Git.

The induction-versus-maintenance aggregate population boundary is exercised separately on real
provider data in `docs/43_uc_phase_population_alignment.md`. The independent maintenance-trial
replication is now complete in `docs/44_uc_maintenance_risk_difference_replication.md`; it adds an
absolute percentage-point effect without pooling or same-candidate replication claims. The next
breadth milestone is a second immune/inflammatory disease with a preregistered endpoint and
population contract.
