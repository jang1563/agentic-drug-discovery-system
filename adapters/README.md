# Adapters

Adapters translate external tools, databases, and models into the environment's observation schema.

## Implemented adapters

Callable adapters used by the sickle cell disease vertical slice
(`docs/12_scd_vertical_slice.md`):

- `opentargets_adapter.py` — Open Targets disease identity/load profile and target-disease
  association, with explicit initialized-disease mismatch and dataset-unavailable states.
- `chembl_adapter.py` — ChEMBL molecule, mechanism, normalized target profile, and
  target-activity lookup.
- `ctgov_adapter.py` — contextual ClinicalTrials.gov search/cache observations with source
  intervention/condition identity, status, results, whyStopped, and primary-endpoint fields. This
  unpinned path cannot satisfy the default clinical advance gate.
- `ema_epar_adapter.py` — EMA EPAR matched-row regulatory status; a no-match is
  reported as unresolved rather than proof of no filing.
- `ema_ledger.py` — curated EMA reversal ledger.
- `boltz_adapter.py` — GPU-gated endpoint adapter with structured `predict_binding_record()`
  statuses, service-defined affinity units, redacted endpoint errors, and an explicitly
  non-predictive ChEMBL metadata fallback. The legacy text renderer remains available.
- `molprops_adapter.py` — local (CPU) RDKit druglikeness signal: QED, MW, logP,
  H-bond donors/acceptors, Lipinski violations. RDKit is required; no GPU is.
- `pinned_evidence_adapter.py` — dependency-free reader for the public
  `adds.pinned-evidence.v1` manifest. It validates exact fields, source versions, SHA-256 values,
  observation/availability dates, evidence-specific contexts, and typed summary fields without
  storing raw scientific payloads. Preclinical records carry explicit assay/model-system ids and
  links to the canonical disease, target, candidate, and organism context. Manifest normalization
  is shared with `agentic_drug_discovery/ingestion.py`, which captures external source bundles and
  compiles reviewer-authored payload-free records.
- `agentic_drug_discovery/cdc_mmwr.py` — provider-specific verifier for reviewer-authored CDC MMWR
  disease-burden and treatment-gap records. It binds a captured HTML receipt to article citation
  metadata, section, excerpt, value, unit, geography, and reference period, then emits a generic
  payload-free ingestion job with the excerpt removed and hashed.
- `agentic_drug_discovery/ncbi_pubmed.py` — provider-specific verifier for reviewer-authored NCBI
  PubMed treatment-gap records. It binds an exact EFetch XML request to direct PMID, PMCID, DOI,
  title, electronic-publication, structured-abstract, typed-value, and context-anchor checks, then
  removes and hashes reviewer evidence text.
- `agentic_drug_discovery/chembl_activity.py` — provider-specific verifier for one release-bound
  ChEMBL status/activity/assay/document/molecule/target bundle. It cross-checks linked ids, a clean
  standardized endpoint, source assay classification, functional-readout evidence, candidate
  aliases, direct single-protein target identity, and publication lineage, then removes assay text.
- `agentic_drug_discovery/ncbi_pubmed.py` also implements the disease-model path. It binds one exact
  EFetch record to typed model, candidate, dose, route, frequency, duration, endpoint, variation,
  p-value, and publication lineage fields, then removes reviewer excerpts and anchors.
- `agentic_drug_discovery/clinicaltrials_gov.py` — provider-specific verifier for one exact API
  study receipt. It reconciles NCT/version, candidate aliases, condition, protocol and result arms,
  denominators, population, posted endpoint, and statistical analysis, then removes source payload
  structure from the generic job.
- `agentic_drug_discovery/clinical_portfolio.py` — strict multi-trial bundle verifier that reuses the
  single-trial extractor, requires an exact pairwise source-disjoint trial set bound to one approved
  endpoint mapping, and emits one payload-free portfolio ingestion job.
- `agentic_drug_discovery/clinical_endpoint_mapping.py` — deterministic compiler and replay validator
  for reviewer-approved endpoint-family ontology bindings. It retains identity and provenance only,
  and records external ontology-authority verification as unresolved.
- `clinical_synthesis_adapter.py` — local, deterministic normalizer for explicitly reviewed
  endpoint mappings and multi-trial endpoint/safety selections. It registers the mapping first,
  requires synthesis to reference that exact mapping, and re-reads source measurements from
  committed trial-design ledgers.
- `execution_registry.py` — typed bindings that register explicitly supplied adapter instances as
  state-bound `ToolContract` operations. It exposes a composite ChEMBL
  molecule-target-mechanism profile that verifies target symbol, organism, and single-protein
  scope for modality selection; the older molecule-mechanism profile cannot satisfy the default
  target-continuity gate alone. It allows target activity counts at preclinical review, prefers structured
  Boltz output, normalizes unavailable/error/unknown states without retaining endpoint details,
  exposes pinned unmet-need and candidate functional-effect profiles, and never converts raw
  payloads into scientific evidence automatically.

**Data boundary:** adapter *code* ships, but the cached data snapshots and case
banks it reads do not (see `docs/release_boundary.md`). On a clean public clone
the adapters import and compile but are illustrative-only without a user's own
cached snapshots or live API access.

## Adapter groups (layout)

- `databases/`: retrieval, entity lookup, assay and literature records.
- `sfm_models/`: protein, chemical, cell, genome, and perturbation models.
- `llm_models/`: prompt, tool-calling, vLLM, and policy interfaces.
- `external_tools/`: chemistry, structure, ADMET, and analysis tools.

The typed registry now supplies a common contract for:

- input schema
- output schema
- provenance fields
- error format
- explicit unavailable and failed states
- action type, allowed stages, and cost limit
- immutable request fingerprint and output hash

Stage-specific scientific interpretation remains separate. The core semantic mapper registry
currently recognizes selected Open Targets, ChEMBL, RDKit molprops, ClinicalTrials.gov, EMA,
Boltz, and pinned-evidence operations. Open Targets disease profiles establish identity context,
not unmet need; ChEMBL activity counts establish target activity volume, not candidate functional
effect; and Boltz prediction records are contextual-only. Pinned profiles require two exact,
independent source records and use manifest dates rather than caller-declared context dates. The
preclinical profile also requires typed endpoints, candidate-alias continuity, and disjoint
canonical upstream publication lineages.
The mapper emits evidence-backed disease, assay, and model-system records only after accepted ledger
identities agree. Unmapped, incomplete, ambiguous, post-cutoff, same-source, or cross-context
profiles fail closed.
Legacy ClinicalTrials.gov search mappings reconcile source intervention, condition, and NCT but
remain contextual. The pinned `clinical_trial_design` mapping requires an exact receipt and emits
intervention, trial, candidate/comparator arm, population, and endpoint records as one atomic
design. EMA mappings extend only an accepted intervention whose source asset or INN matches the
request. Promotion context alone cannot establish either identity.
The `clinical_endpoint_mapping_v1` mapping commits an approved, exact source-disjoint binding before
the `clinical_benefit_risk_synthesis` mapping can run. Synthesis recompiles each bound selection from
committed trial-design records and preserves trial-level hazard ratios, confidence intervals, arm
measurements, serious-event counts, and source hashes while prohibiting automatic endpoint mapping,
cross-trial pooling, benefit-risk scoring, and clinical acceptability inference.

Most live adapters remain GitHub-only in the current Hugging Face split. The Hub package includes
the dependency-free pinned-evidence adapter, its typed registry binding, schema, synthetic example,
source-receipt/compiler contracts, and tests; it does not include live endpoint configuration, raw
source bundles, real provider jobs, or ingestion runs. The CDC MMWR, NCBI PubMed treatment-gap,
ChEMBL functional-activity, NCBI PubMed disease-model, and ClinicalTrials.gov trial-design and
portfolio schemas, synthetic fixtures, extractors, and fail-closed tests are included. The local
endpoint-mapping and clinical-synthesis contracts, compilers, replay checks, and synthetic tests are
also included.
