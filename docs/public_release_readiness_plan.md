# Public Release Readiness Plan

Status: 0.3.0.dev2 public development release active after exact-package approval
Release posture: GitHub and Hugging Face public; publish refreshes only from reviewed Git commits after all blocking gates pass
Target surface: public GitHub repository with a commit-pinned Hugging Face Dataset mirror

## Objective

Maintain this repository as a premium public research artifact: readable by humans, inspectable by machines, and conservative about sensitive or nonessential internal material. Public updates should communicate the system architecture, safety boundary, schemas, verifier contracts, adapter interfaces, and audit path without exposing raw source snapshots, evaluator-only labels, generated trajectories, scheduler logs, local paths, credentials, or unpublished working notes. The Hugging Face mirror remains a Dataset-card artifact mirror rather than a model release.

## Public Surface

The public GitHub surface includes:

- Top-level orientation: `README.md`, `PROJECT_BRIEF.md`, `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `CITATION.cff`, and `CHANGELOG.md`.
- Design, evidence, and boundary docs: `docs/00_*` through `docs/07_*`,
  `docs/11_*` through `docs/34_*`, the payload-free preclinical, clinical provider, and sealed
  policy-evaluation snapshots, `docs/public_evidence_summary.json`, `docs/release_boundary.md`, and
  this plan.
- Machine-readable release metadata: `release_manifest.json`, `codemeta.json`, and `.zenodo.json`.
- Hugging Face local package: `huggingface/README.md` and `huggingface/release_manifest.json`.
- Executable and scaffold code: `agentic_drug_discovery/`, `tests/`, `adapters/`,
  `chains/`, `rl_env/specs/`, `rl_env/rewards/`, `verifiers/soft/README.md`,
  audit scripts, and the `benchmark/` scorer/tests.
- The clinical evidence closed-loop surface is limited to implementation, schemas,
  compiler-generated synthetic examples, tests, and documentation. Real policies,
  execution batches, provider requests or outcomes, receipts, reviewer refresh
  records, before/after tensors, and transition packages remain excluded.
- The clinical cohort surface is limited to implementation, strict schemas/readers,
  compiler-generated synthetic manifest/report examples, tests, and documentation. Real cohort
  manifests, accepted-state bindings, package diagnostics, source/trial overlaps, and reports
  remain excluded.
- The clinical outcome-evaluation surface is limited to implementation, strict schemas/readers,
  compiler-generated synthetic protocol/submission/manifest/report examples, aggregate summaries,
  tests, and documentation. Real submissions, outcome manifests, unit-level endpoint/safety labels,
  source assessments, curator material, and per-unit scores remain excluded.
- The dependence-aware outcome-uncertainty surface is limited to implementation, strict
  schemas/readers, public protocol and aggregate-report examples, tests, and documentation. Real
  dependence manifests, unit-to-cluster assignments, cluster-level diagnostics, and unit-level
  metric contributions remain evaluator-only.
- The prospective clustered-board design surface is limited to bounded implementation, strict
  protocol/report/summary schemas and readers, aggregate synthetic examples, tests, and
  documentation. Real scenario ranges, pilot elicitation, replicate records, and gate-selection
  deliberations remain excluded.
- The informative-evaluability and dependence-closure stress surface is limited to bounded
  implementation, strict protocol/report/summary schemas and readers, aggregate synthetic
  examples, tests, and documentation. Real missingness-model elicitation, hidden-dependence
  working records, replicate records, and correction-selection deliberations remain excluded.
- The prediction-stratified binary pattern-mixture surface is limited to exact stress-bound
  implementation, strict protocol/report/summary schemas and readers, aggregate synthetic
  examples, tests, and documentation. Real log-IMOR elicitation, prediction-stratum working
  records, latent outcomes, and correction-selection deliberations remain excluded.
- The pattern-mixture sampling-uncertainty surface is limited to exact stress/protocol/report-bound
  implementation, strict protocol/report/summary schemas and readers, aggregate synthetic
  cluster-jackknife examples, tests, and documentation. Real dependence manifests, cluster
  influence records, elicited log-IMOR ranges, and replicate- or cluster-level results remain
  excluded.
- GitHub automation: `.github/workflows/release-audit.yml`, pull request template, and issue templates.
- Empty directory markers needed to preserve the scaffold layout.

## Excluded Surface

The following stay outside Git unless a separate audited release package explicitly promotes a public-only artifact:

- Full case banks, raw source snapshots, locked episodes, hidden gold, evaluator-only labels, and generated reward/verifier outputs.
- Raw source bundles, real provider review jobs, ingestion runs, multi-trial portfolio selections,
  endpoint-family reviewer approvals, ontology-authority resolutions, and reviewer working files.
- Real policy checkpoints and policy-run artifacts containing complete state or tool ledgers.
- Real sealed boards, cached episode packets, label vaults, commitment nonces, policy submissions,
  and per-episode evaluation outputs.
- Real held-out curator identities, affiliation records, attestations, evidence snapshots, votes,
  rationales, adjudications, curation manifests, and per-episode curation outputs.
- Real clinical decision and cohort policies, manifests, accepted-state bindings, package
  diagnostics, evidence tensors, action catalogs, compiled packages, and cohort reports.
- Real clinical prediction submissions, outcome manifests, unit-level endpoint/safety labels,
  source assessments, curator materials, and per-unit clinical outcome evaluations.
- Real clinical outcome dependence manifests, unit-to-cluster assignments, cluster-level results,
  and unit-level uncertainty contributions.
- Real clinical outcome design scenarios, pilot parameter elicitation, replicate-level simulation
  records, and non-public gate-selection deliberations.
- Real clinical outcome stress scenarios, missingness-model elicitation, hidden-dependence working
  records, replicate-level simulation records, and correction-selection deliberations.
- Real clinical outcome sensitivity protocols, log-IMOR elicitation, prediction-stratum working
  records, latent outcomes, and correction-selection deliberations.
- Local working notes, imported research packs, private opportunity records, and machine-specific source maps.
- Scheduler logs, root-level run outputs, generated caches, Python bytecode, and large experiment directories.
- Credentials, API tokens, `.env*`, key material, local account names, absolute local paths, and internal compute-location breadcrumbs.

## Blocking Gates

Before merging or uploading a change to either public surface:

1. Boundary audit passes:

   ```bash
   python3 -m pip install -e ".[test]" -e ./benchmark build ruff
   python3 scripts/audit/github_release_file_audit.py
   python3 scripts/audit/validate_hf_release_package.py
   python3 -m unittest discover -s tests -v
   python3 -m ruff check agentic_drug_discovery tests adapters/boltz_adapter.py adapters/chembl_adapter.py adapters/opentargets_adapter.py adapters/execution_registry.py adapters/pinned_evidence_adapter.py adapters/clinical_synthesis_adapter.py scripts/audit
   python3 -m pytest -q benchmark/tests
   python3 -m build --wheel . --outdir /tmp/agentic-core-dist
   python3 scripts/audit/smoke_test_core_wheel.py --wheel-dir /tmp/agentic-core-dist
   python3 scripts/audit/build_hf_release_package.py --output /tmp/agentic-hf-release-package --force
   python3 scripts/audit/validate_hf_release_package.py --package /tmp/agentic-hf-release-package
   ```

2. Whitespace and Python sanity checks pass:

   ```bash
   git diff --check
   python3 -m compileall agentic_drug_discovery adapters chains benchmark/src scripts/audit tests
   ```

3. Candidate file set is reviewed:

   ```bash
   git ls-files --cached --others --exclude-standard
   git status --short --ignored
   ```

4. Release metadata is complete:

   - `release_manifest.json`, `codemeta.json`, `.zenodo.json`, and `huggingface/release_manifest.json` reflect the intended public scope.
   - `CITATION.cff` has correct public citation metadata.
   - `SECURITY.md` gives safe reporting guidance without publishing direct sensitive-contact details.
   - `LICENSE` is present and the license id is consistent across metadata.

5. Human review confirms the repo does not contain sensitive content, unpublished evaluator material, or local infrastructure breadcrumbs.

## Premium Finish Checklist

- Repository description and topics clearly frame this as safety-oriented decision infrastructure, not an autonomous wet-lab or hazardous-design tool.
- Branch protection requires the release audit workflow before merging.
- The next public tag is cut only after the blocking gates pass from a clean checkout.
- README links users to the release boundary, manifest, and audit command within the first screen.
- Any Hugging Face mirror update is uploaded only after the exact GitHub candidate commit is clean, with a Dataset card that repeats the same boundary.

## Current Work Plan

1. Harden the already-public GitHub surface through a reviewed pull request.
2. Preserve local research and run artifacts without committing them.
3. Build the Hub mirror from the merged Git commit, not working-tree bytes.
4. Upload the refreshed public mirror and verify its exact file/hash manifest.
5. Cut a versioned GitHub/Hugging Face release only after clean-checkout checks
   pass and the source and dataset revisions are immutable.
