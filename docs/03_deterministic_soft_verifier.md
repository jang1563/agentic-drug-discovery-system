# Deterministic + Soft Verifier Design

## Deterministic Verifiers

Use deterministic verifiers for checks that should be exact or nearly exact.

Examples:

- schema validity
- required fields
- entity normalization
- unit conversion
- chemical validity
- sequence validity
- database provenance
- duplicate/leakage checks
- tool output parseability
- budget and action constraints

## Soft Verifiers

Use soft verifiers for judgments that are probabilistic, contextual, or evidence-weighted.

Examples:

- evidence sufficiency
- target plausibility
- mechanism plausibility
- structure/interface plausibility
- ADMET risk
- uncertainty calibration
- novelty
- actionability
- safe stopping

## Routing Rule

Hard failures should block or repair a step. Soft failures should reduce reward, request more evidence, trigger a different tool, or escalate to review depending on severity.

## Avoided Pattern

Do not let the LLM be the only verifier. The LLM can interpret or summarize verifier outputs, but the verifier layer should remain separately logged and inspectable.

