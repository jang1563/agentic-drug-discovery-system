# Soft Verifiers

Soft verifiers score judgment-heavy evidence dimensions that should shape reward
or reviewer attention, but should not by themselves lock an episode.

## Current Checks

- Curation-side rubrics combine public outcome alignment, p-value direction,
  endpoint type, entity ambiguity, and invalid-value trap status into
  reviewer-ready clinical relevance scores.
- Class-specific non-locking reviewers can score reject, verify, and defer
  candidates, including mixed-evidence, related-but-indirect, and bounded
  no-evidence boundaries.
