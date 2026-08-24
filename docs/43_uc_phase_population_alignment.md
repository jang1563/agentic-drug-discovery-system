# Ulcerative Colitis Phase-Population Alignment

Status: externally executed on 2026-08-20 against one public ClinicalTrials.gov record

Scope: induction and maintenance analyses from `NCT02435992`, kept as separate phase-bound
populations with exact endpoint and serious-adverse-event arm identities

Machine snapshot: `docs/uc_phase_population_validation_snapshot.json`

## Research Question

Can one registry record support both induction and maintenance evidence without silently treating
study enrollment, endpoint denominators, safety denominators, or participant identities as the
same population?

The executable answer is yes at the aggregate contract level. The provider now derives a
`population_alignment` object from the selected endpoint and safety arms. Promotion recomputes
that object, and endpoint mapping and benefit-risk synthesis reject phase or population rebinding.

## Real-Source Results

| Field | Induction | Maintenance |
| --- | --- | --- |
| Trial | `NCT02435992` | `NCT02435992` |
| Registry `versionHolder` | `2026-08-20` | `2026-08-20` |
| Treatment phase | Induction, Week 10 | Maintenance, Week 52 |
| Endpoint groups | `OG000`, `OG001` | `OG003`, `OG004` |
| Candidate/comparator endpoint N | `429` / `216` | `230` / `227` |
| Endpoint analysis N | `645` | `457` |
| Safety groups | `EG000`, `EG001` | `EG003`, `EG004` |
| Candidate/comparator safety at risk | `429` / `216` | `230` / `227` |
| Odds ratio | `3.586` | `2.755` |
| 95% confidence interval | `1.938` to `6.636` | `1.767` to `4.294` |
| P-value | `= 0.0001` | `= 0.0001` |
| Computed direction | `benefit` | `benefit` |
| Stage outcome | committed `ADVANCE` | committed `ADVANCE` |

The registry-wide enrollment is `1012`, which is retained separately from both analysis
populations. Matching endpoint and safety counts within each role are recorded as
`rolewise_counts_match: true`; they do not prove that the aggregates contain exactly the same
individuals, so `same_participants_inferred` remains `false`.

## Implemented Contract

Phase-bound records carry one exact alignment object across trial design, analysis population,
endpoint, and safety summary:

```json
{
  "treatment_phase": "maintenance",
  "study_enrollment_count": 1012,
  "endpoint_analysis_participant_count": 457,
  "safety_at_risk_participant_count": 457,
  "rolewise_counts_match": true,
  "same_participants_inferred": false
}
```

The verifier recomputes endpoint denominators and safety at-risk counts from typed
candidate/comparator arms. Any missing layer, phase mismatch, count tampering, population
rebinding, or unsupported field fails closed. Legacy records remain readable only when all four
layers omit the new phase-bound metadata together.

The arm-title reconciler also handles the observed registry asymmetry where the efficacy title is
`RPC1063 (Maintenance Period)` and the safety title is
`Intervention (Maintenance Period): RPC1063 1mg`. It removes bounded phase and dose qualifiers
while preserving source group ids, roles, source titles, counts, and numeric tokens inside drug
identifiers such as `RPC1063`.

## Artifact Identity

Raw source bytes and review jobs remain external. The same byte-identical source capture was used
for both analyses.

| Artifact | Induction SHA-256 | Maintenance SHA-256 |
| --- | --- | --- |
| Exact source JSON | `fa48160bf981705439b8c3a759a2a17fbedead3d77cb3ee484afaeef16dd533c` | `fa48160bf981705439b8c3a759a2a17fbedead3d77cb3ee484afaeef16dd533c` |
| Canonical review job | `9e0ba1fd2c422f068014774836780f12e23afb7275aee60579f4eb6f874cf1bd` | `f7f81ded7b3f2252f4dadb5465ba0f03683a3a928d978688056c27f049c6dde3` |
| Canonical extracted job | `d4b286991ab9a537d643dfabc00bf4600d3aec0259a2397e892ee6ae43d1fae6` | `43dfcb96048442997d4c698e46dcdc523e9c62fbed504273d3458084a95b3cfd` |
| Canonical manifest | `7f7f489e8d7f118ca3f9c3754ae8e412e7524020f363600b94b407d3225fd924` | `3bdc891244fd1a9b636d3980a19fa9730eac2d0d4a4d3952befa21fdbfa574e2` |

## Scientific Boundary

These analyses share one NCT id and one source payload, and the registry explicitly notes
re-randomization before maintenance. They therefore count as one trial, not two independent
replications. The system does not pool the two odds ratios, infer participant overlap or
longitudinal exchangeability, compare phase effects, or infer efficacy, safety acceptability, or a
treatment recommendation.

The independent-trial maintenance step is now complete in
`docs/44_uc_maintenance_risk_difference_replication.md`, using a source-disjoint trial and an
additive percentage-point effect. The next breadth milestone is a second immune/inflammatory
indication with preregistered endpoint-family, population, estimand, and safety-window mappings.
Risk-difference evidence remains outside bounded VOI planning until an additive-scale precision
policy is preregistered.
