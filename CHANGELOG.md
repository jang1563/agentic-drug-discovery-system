# Changelog

All notable public-surface changes to this repository will be documented here.

## Unreleased

- Added an installable `agentic_drug_discovery` execution core with typed evidence, claims,
  candidates, accepted-packet/action/decision/verifier ledgers, decision packets, program state,
  configurable stage gates, and fail-closed transitions across the eight-stage discovery chain.
- Added an explicitly non-benchmark SCD-shaped control-plane demo plus regression coverage for
  temporal leakage, stale packets, evidence polarity and conflicts, upstream pivots, action
  provenance, candidate-presence gates, budgets, terminal states, duplicate identifiers,
  serialization, and malformed or failing verifiers.
- Added a blocking isolated-wheel smoke test so CI validates the installed console entry point,
  not only the editable source tree and wheel build.
- Added typed tool contracts, state/version-bound requests, structured outcomes, explicit
  cache/live/local modes, payload hashes, and an immutable execution ledger.
- Added conservative bindings for the existing Open Targets, ChEMBL, ClinicalTrials.gov, EMA,
  Boltz-2, and RDKit molprops adapters; unresolved legacy return values remain unavailable rather
  than being promoted to evidence, and endpoint error details are redacted from typed outcomes.
- Added explicit tool-outcome-to-evidence promotion, strict JSON record ingestion, replay-bundle
  integrity checks for status, cost, contract, chronology, and provenance links, plus the
  `adds-replay-bundle` machine-readable CLI.
- Added a bounded planner that validates state/version, stage, contracts, duplicate requests,
  chronology, step limits, and the complete required-call budget before invoking any tool.
- Added operation-specific semantic mappings for Open Targets, ChEMBL, RDKit molecular properties,
  ClinicalTrials.gov, EMA, and structured Boltz output. Boltz predictions remain contextual-only
  and cannot satisfy hard stage readiness.
- Added a bounded stage runner that preserves an attempt journal, stops after required tool
  failure, rejects missing or post-cutoff promotion context before invocation, preserves plan
  metadata, aggregates decisions conservatively, and can recover only readiness-blocked advance
  proposals to an accepted, replayable defer packet.
- Added a typed bounded program runner that chains ordered stage plans over one cumulative execution
  ledger, validates state and packet continuity, stops on non-advance or blocked outcomes, and
  requires exact accepted-packet replay of the recorded final state.
- Added typed deterministic policy replanning over paused/blocked observations, predeclared
  replacement steps, per-rule/global revision limits, append-only queue history, SHA-256-bound
  checkpoints, duplicate-key/tamper/stale-token rejection, and exact checkpoint resume.
- Added a cutoff-safe sealed evaluation contract with role-neutral opaque episode and pair
  identities, externally separated evaluator labels, salted commitments, board-bound submissions,
  explicit per-episode confidence, strict JSON Schemas and envelope readers, and synthetic
  tamper/leakage tests.
- Executed an external four-pair/eight-episode retrospective policy board over the real senicapoc
  continuous program and PALOMA-2/PALOMA-3 portfolio. The governed deterministic output was exact
  on 8/8 episodes with zero unsafe advances, while always-advance was exact on 1/8 with 7/7 unsafe
  advances and defer-safe was exact on 4/8 with zero unsafe advances. Only payload-free aggregate
  metrics, implementation/artifact hashes, gate outcomes, and explicit small-N limitations are
  released; this is not a discovery-performance or calibration claim.
- Added Open Targets disease-profile and ChEMBL molecule-mechanism profile bindings plus conservative
  disease-context, modality-mechanism, and preclinical activity-volume mappings. Disease identity
  cannot establish unmet need, and target activity volume cannot establish candidate functional
  effect.
- Added a five-stage real-registry integration path that advances through target, modality,
  candidate, and lead gates, then intentionally defers at the preclinical functional-effect gate.
- Added composite disease-context and preclinical hard gates. Each requires two linked component
  evidence predicates, two distinct source ids, two distinct valid source-content SHA-256 values,
  and no exact-byte relabeling. The preclinical gate additionally requires typed endpoint
  semantics, candidate alias resolution, and disjoint canonical upstream publication lineages.
- Added a dependency-free, payload-free pinned-evidence manifest adapter, JSON Schema, synthetic
  example, registry contracts, and conservative semantic mappings for disease burden plus treatment
  gap and candidate-target function plus disease-model effect.
- Added the dependency-free `adds-pinned-ingestion` capture/compiler path. It stores exact source
  bytes only in immutable external bundles, emits strict payload-free receipts, verifies bytes and
  chronology during compilation, and produces a pinned manifest plus mandatory human-review report.
- Hardened ingestion against signed-token URL parameters, invalid or raced size bounds, obfuscated
  raw-payload keys, non-finite summary values, and partial two-output compilation. Exact source bytes
  relabeled under different source ids now remain one independent-content unit and defer at
  composite gates.
- Added the first provider-specific ingestion contract for captured CDC MMWR HTML. It verifies
  receipt and article identity, DOI-bound source version, citation metadata, section, excerpt,
  numeric value, unit, geography, and reference period before emitting a payload-free generic job
  with an excerpt hash. Noncanonical ports, inexact DOI versions, prepublication retrieval,
  provider-field spoofing, and malformed DOI suffixes fail closed; CLI reports bind both source and
  sanitized output SHA-256. Synthetic tests cover matched independent-source advance and
  same-document defer behavior; real source bytes and reviewer jobs remain outside the release.
- Added a strict NCBI PubMed EFetch XML treatment-gap contract. It reconciles direct PMID, PMCID,
  DOI, title, canonical URL, electronic publication date, exact request identity, and
  retrieval-date-bound source version; rejects entities, retractions, ambiguous records, duplicate
  sections, provider-field spoofing, and unsupported predicates; and verifies reviewer-selected
  METHODS/RESULTS excerpts, typed comparator/value/unit, and context anchors before removing all
  excerpt and anchor text. Synthetic tests pair context-matched advance with cross-population
  defer, while an external PMID 32147964 extraction plus the broader CDC burden correctly abstains
  with `pinned_unmet_need_context_mismatch`.
- Added a strict ChEMBL functional-activity contract over one release-bound status/activity/assay/
  document/molecule/target bundle. It cross-checks linked ids, clean standardized point estimates,
  source assay classification, direct single-protein assignment, candidate aliases, target
  components, and publication lineage before stripping assay evidence text.
- Added a strict NCBI PubMed disease-model contract for one typed in-vivo exposure and endpoint. It
  checks direct article identity, retraction state, candidate/model anchors, dose, route, frequency,
  duration, endpoint variation, and p-value before stripping reviewer excerpts and anchors.
- Added a matched preclinical provider-pair integration test. Independent synthetic ChEMBL and
  PubMed lineages advance to clinical strategy; changing only the model record's upstream lineage
  defers with `pinned_functional_effect_lineage_not_independent` and promotes no evidence. A
  corresponding real-source validation was executed externally; only payload-free ids, hashes,
  outcomes, and limitations are documented publicly in a machine-readable snapshot.
- Added a strict ClinicalTrials.gov API study contract. It binds one exact receipt and registry
  version to NCT, candidate aliases, condition, protocol/result arms, denominators, population,
  posted primary endpoint, statistical analysis, and selected-arm serious-adverse-event aggregates
  before emitting a payload-free job. Source, NCT, arm, result/adverse-event group, analysis, and
  safety-count drift fail closed.
- Hardened source-pinned clinical promotion so every declared candidate alias must resolve through
  the accepted candidate id/name or its pre-approved identity aliases; mixing a canonical alias
  with an unapproved subject alias no longer authorizes the latter. Source disease aliases require
  an approved disease-name binding.
- Added bounded source-pinned clinical promotion with canonical intervention, trial, candidate and
  comparator arm roles, population, endpoint, safety, and safety-arm records projected as one
  atomic design. Clinical advance requires both `clinical_evidence_assessed` and
  `clinical_safety_assessed` from the exact study, without inferring safety acceptability. One exact
  external NCT01844505 snapshot advances and a missing-safety control defers with zero partial
  state; public documentation retains only typed values, hashes, outcomes, and limits.
- Added explicit multi-trial endpoint/safety harmonization at regulatory review. A local
  deterministic adapter and semantic mapper recompile reviewed trial/design/endpoint/safety
  selections into append-only study and synthesis records that retain hazard ratios, confidence
  intervals, source arm measurements, serious-event counts, evidence ids, and source hashes.
  Pairwise source-disjointness, exact replay, no automatic endpoint mapping, no pooling, no
  benefit-risk score, and no clinical acceptability inference are enforced by typed models and a
  recompiling continuity verifier; mismatch, overlap, pooling, forgery, and removal attacks fail
  closed.
- Added atomic ClinicalTrials.gov portfolio extraction over the exact set of independently reviewed
  single-trial jobs and external source bundles. Missing, extra, rebound, or content-hash-overlapping
  inputs fail before a payload-free generic job is written.
- Added reviewer-approved endpoint-family ontology mapping as an append-only typed ledger. Mapping
  records retain reviewer/time identity, exact trial/design/endpoint/safety bindings, endpoint and
  safety fingerprints, source evidence, and source hashes; direct commits, rebinding, mutation, and
  removal fail closed. Synthesis now requires `endpoint_mapping_id` and an exact approved binding-set
  match. Ontology identities are preserved but not authority-resolved automatically.
- Promoted pinned-manifest normalization into the executable core so direct adapter input and
  compiler output share raw-field, local-path, size, predicate, source, and chronology checks. Added
  source-receipt, ingestion-job, and review-report schemas with synthetic examples.
- Multi-source outcomes now require explicit per-evidence source selection. External source hashes
  are preserved as declared instead of silently substituting the tool-payload hash.
- Added a replayable eight-stage provider-backed integration from disease context through
  source-pinned clinical endpoint/safety design and EMA regulatory review. The single cumulative
  ledger reaches `COMPLETED` with 19 evidence events, nine claims, and all typed identities
  preserved. The synthetic control fixture and matched provenance tests do not claim scientific
  performance.
- Added matched compiled-manifest coverage: independent captured disease sources advance, while
  changing only the treatment-gap receipt to reuse the burden source defers with balanced accuracy
  1.0. This is a deterministic provenance contract test, not a scientific result.
- Added an evidence-backed `TargetRecord` ledger spanning Open Targets Ensembl identity, ChEMBL
  target-profile verification, candidate linkage, lead preservation, and pinned preclinical
  identity checks. Accepted namespace bindings cannot be removed, rebound, or shared across
  canonical targets.
- Added the typed `molecule_target_mechanism_profile` operation, target-identity JSON Schema and
  synthetic example, stage namespace gates, and matched symbol-match/symbol-mismatch coverage.
  Legacy molecule-mechanism observations no longer satisfy the default modality gate alone.
- Added evidence-backed `DiseaseRecord`, `AssayRecord`, and `ModelSystemRecord` ledgers, strict
  serialization, packet promotion, replay projection, and default stage gates. Every advance now
  requires one canonical disease; preclinical advance additionally requires current-packet assay
  and model-system records linked to the same viable candidate and pinned component evidence.
- Added a discovery-context identity schema and synthetic example plus fail-closed coverage for
  disease/model rebinding, namespace collision, unknown-candidate assay evidence, and a matched
  assay-target-link success/failure pair.
- Added evidence-backed `InterventionRecord`, `TrialRecord`, and atomic `TrialDesignRecord` ledgers
  with typed arm, population, endpoint, safety, and safety-arm children across strict
  serialization, packet promotion, replay projection, and default clinical/regulatory gates.
  Legacy ClinicalTrials.gov search observations are contextual; clinical advance requires a
  source-pinned endpoint/safety design.
- Expanded the clinical identity schema and synthetic example plus fail-closed coverage for
  intervention rebinding, trial namespace collision, unknown-intervention linkage, arm-role
  rebinding, endpoint/safety-support removal, atomic missing-safety defer, and EMA source-identity
  mismatch.
- Added exact-context matched success/failure episode contracts and arm/pair evaluation summaries
  with cutoff, ontology-key, evaluator-label, and failure-cause validation.
- Added the dependency-free `adds-bounded-agent-demo` console path and isolated-wheel coverage for
  the static demo, bounded agent loop, and replay CLI.

## 0.2.0 - 2026-07-14

- Hardened `ctdbench` 0.2.0 against class-selective abstention by separating
  all-class, conditional, and coverage-adjusted balanced accuracy; added
  per-class coverage, fail-closed label validation, and an immutable default
  Hugging Face dataset revision.
- Added public release boundary documentation, release manifest, security policy, contribution guide, citation metadata, license, and archive metadata.
- Added callable tool/database adapters (Open Targets, ChEMBL, ClinicalTrials.gov, openFDA, EMA EPAR) and multi-stage flow orchestrators (discovery_flow, episode_flow) for the first public decision-environment surface.
- Added a local RDKit-based molecular-property adapter (QED, MW, logP, H-bond donors/acceptors, Lipinski) giving the compound-design stage a computable, no-GPU druglikeness signal.
- Added `docs/12_scd_vertical_slice.md` documenting the audited end-to-end sickle cell disease (SCD) retrospective benchmark slice and prospective decision-support demo.
- Added `docs/13_target_id_governance_node.md` and
  `docs/public_evidence_summary.json` as small-N, aggregate-only scientific claim
  anchors with explicit provenance limits.
- Added the installable `benchmark/` scorer and tests for the separately hosted
  clinical-trial decision dataset; the external dataset's Croissant metadata is
  intentionally excluded from this artifact mirror.
- Added `scripts/audit/validate_vertical_slice_doc.py` to keep public benchmark numbers caveats-first and small-N scoped.
- Added `docs/release_trust_report.md` and a commit-object-based
  `scripts/audit/build_hf_release_package.py` so each Hugging Face payload is
  tied to an exact source commit/tree with per-file SHA-256 and byte sizes.
- Disambiguated stopped/withdrawn/revoked programs from serious safety signals
  on still-approved assets in both decision prompts.
- Strengthened local and CI release-audit gates for sensitive content, generated artifacts, machine-specific breadcrumbs, and public metadata completeness.
