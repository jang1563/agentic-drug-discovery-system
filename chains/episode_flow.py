#!/usr/bin/env python3
"""Episode flow orchestrator + agent policy interface (Track B).

Runs one episode (a MASKED agent packet — no family tells) through a policy that
may call tools, producing a trajectory (ordered steps + provenance) and a terminal
action. This is the interface an LLM policy slots into later: swap EvidenceReadingPolicy
for an LLMPolicy that calls the same adapter tools.

Terminal action space: advance / stop / defer / request_more_evidence / flag.
"""
from __future__ import annotations


class Trajectory:
    def __init__(self, episode_id):
        self.episode_id = episode_id
        self.steps = []
        self.terminal_action = None

    def log(self, tool, observation):
        self.steps.append({"tool": tool, "observation": observation})

    def finish(self, action, rationale):
        self.terminal_action = action
        self.steps.append({"decision": action, "rationale": rationale})
        return self


class AgentPolicy:
    """Interface. act() receives the masked episode + tool adapter + trajectory."""
    name = "base"

    def act(self, episode, adapter, traj):
        raise NotImplementedError


class ConstantPolicy(AgentPolicy):
    def __init__(self, action):
        self.action = action
        self.name = f"constant:{action}"

    def act(self, episode, adapter, traj):
        return traj.finish(self.action, "constant")


class EvidenceReadingPolicy(AgentPolicy):
    """Deterministic reasoner over the MASKED surface + tools. No family labels used."""
    name = "evidence_reader"

    def act(self, episode, adapter, traj):
        ev = (episode.get("masked_packet") or {}).get("evidence", {}) or {}
        drug, cond = episode.get("asset"), episode.get("condition")

        # 1) implausible value in a tool observation -> flag
        tobs = ev.get("tool_observation")
        if tobs:
            checks = adapter.check_value_plausibility(tobs.get("records"), tobs.get("value_validity_rule"))
            traj.log("check_value_plausibility", checks)
            if any(c["out_of_range"] for c in checks):
                return traj.finish("flag", "an observed value violates its declared validity range")

        # 2) resolve direct drug x condition trials — prefer the packet's own matched
        #    NCTs (the agent's prior query result), else search the trials DB.
        direct_ncts = []
        for q in ev.get("queries", []) or []:
            direct_ncts += (q.get("direct_text_match_nct_ids") or [])
        if not direct_ncts:
            direct_ncts = [h["nct"] for h in adapter.search_trials(drug, cond)]
        sigs = [s for s in (adapter.primary_significance(n) for n in dict.fromkeys(direct_ncts)) if s]
        traj.log("resolve_trials", {"drug": drug, "condition": cond,
                                    "n_trials": len(direct_ncts), "results": sigs[:6]})
        scored = [s for s in sigs if s["significant"] is not None]
        if scored:
            sig = [s for s in scored if s["significant"]]
            benefit = [s for s in sig if s["direction"] == "benefit"]
            if 0 < len(sig) < len(scored):  # trials disagree -> genuinely mixed
                return traj.finish("request_more_evidence", "mixed results across trials")
            # NOTE: within-trial endpoint-level mixedness (adapter exposes `mixed_within`) is
            # deliberately NOT branched here — it entangles with stop/advance and lowers overall
            # accuracy; the mixed-vs-stop boundary is an interpretive (human) axis (see track_b README).
            if sig and len(sig) == len(scored) and benefit:
                return traj.finish("advance", "primary endpoint(s) met with benefit direction")
            if not sig:
                return traj.finish("stop", "primary endpoint(s) not met -> efficacy failure")
            return traj.finish("stop", "significant but direction unresolved")
        if direct_ncts:  # trials exist but no parseable results
            return traj.finish("request_more_evidence", "direct trials exist but results unresolved")

        # 3) no direct pair: does the asset appear in other contexts?
        other = adapter.search_asset(drug)
        traj.log("search_asset", {"drug": drug, "n": len(other)})
        if other:
            return traj.finish("request_more_evidence", "same asset tested in other contexts only")

        # 4) no evidence at all -> defer
        return traj.finish("defer", "no direct or related trial evidence found")


def run_episode(policy, episode, adapter):
    traj = Trajectory(episode.get("episode"))
    return policy.act(episode, adapter, traj)
