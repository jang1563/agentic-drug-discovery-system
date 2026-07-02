# Problem Framing

Drug discovery is a long-horizon decision process with many intermediate states, partial observations, uncertain measurements, and expensive downstream validation. A useful agentic system should not be judged only by a final answer; it should be judged by the quality of the path it takes.

## Framing

The project treats drug discovery as an offline agent environment:

- state: structured biological, chemical, literature, assay, and model-derived evidence;
- action: query, retrieve, model, verify, refine, stop, or escalate;
- observation: tool output, SFM representation, database hit, verifier result, or uncertainty update;
- reward: scientific progress, evidence quality, constraint satisfaction, calibration, and cost-aware stopping.

## What This Is Not

- Not wet-lab automation.
- Not a single LLM benchmark.
- Not only protein modeling.
- Not a proposal document.

## Key Design Constraint

Every agent step should be inspectable: what evidence was used, which tool was called, which model produced the representation, which verifier accepted or rejected the step, and what uncertainty remains.
