#!/usr/bin/env python3
"""Multi-stage discovery-decision flow orchestrator (Track B / thin slice).

Traverses a staged episode (target-disease -> compound-target -> clinical -> regulatory),
asking a policy for an advance/stop/defer/request_more_evidence/flag decision at EACH stage
given the TIME-GATED evidence + the accumulated decision history. Produces a trajectory and
scores it against the per-stage and terminal gold.

The interface is the same as the single-stage loop: swap LLMStagePolicy for a hosted
model client. Default LLM backend is the local `claude -p` CLI when available.
"""
from __future__ import annotations
import os, subprocess, json, urllib.request, urllib.parse

ACTIONS = ["request_more_evidence", "advance", "stop", "defer", "flag"]


def _claude(prompt, model=None, timeout=120):
    try:
        cmd = ["claude", "-p"] + (["--model", model] if model else [])
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "").strip()
    except Exception as e:
        return f"error:{e}"
# stage-3 surrogate-only gold accepts either riding the approval OR cautious deferral
ACCEPT = {"advance_with_caution": {"advance", "request_more_evidence", "defer"}}


def accepts(gold, decision):
    return decision in ACCEPT.get(gold, {gold})


class StagePolicy:
    name = "base"

    def decide(self, ctx):
        raise NotImplementedError


class AlwaysAdvancePolicy(StagePolicy):
    name = "always-advance"

    def decide(self, ctx):
        return "advance", "constant"


class AlwaysStopPolicy(StagePolicy):
    name = "always-stop"

    def decide(self, ctx):
        return "stop", "constant"


class LLMStagePolicy(StagePolicy):
    def __init__(self, model=None):
        self.model = model or os.environ.get("SLICE_LLM_MODEL", "claude-sonnet-5")
        self.name = f"llm({self.model})"

    def decide(self, ctx):
        txt = _claude(PROMPT.format(**ctx), self.model).lower()
        action = next((a for a in ACTIONS if a in txt), "defer")
        return action, txt[:80]


PROMPT = """You are a drug-development DECISION agent evaluating the asset "{asset}" for "{disease}".
You are at pipeline stage {stage_name} (stage {stage_i} of {n_stages}). Prior-stage decisions: {history}.

Evidence available at this stage (time-gated to {time_gate} — do NOT assume later knowledge):
{visible_evidence}

Choose EXACTLY ONE terminal action for THIS stage:
- advance: evidence supports proceeding to the next stage.
- stop: the program has failed, been HALTED, WITHDRAWN, or REVOKED — the program
  has ENDED (an efficacy failure OR a safety-driven market withdrawal / regulatory
  revocation both count as stop).
- request_more_evidence: evidence is mixed, contradictory, or surrogate-only — verify before committing.
- defer: evidence is insufficient to decide.
- flag: the evidence is invalid/implausible/corrupt, OR the drug is STILL
  APPROVED / on the market but carries a serious or novel safety signal (e.g. a
  boxed warning, malignancy/mortality signal) warranting caution. A drug that was
  WITHDRAWN or REVOKED is stop, not flag.

Reply with EXACTLY ONE token: advance, stop, defer, request_more_evidence, or flag. No other text."""


def run_flow(episode, policy):
    stages = episode["stages"]
    history, traj = [], []
    for i, s in enumerate(stages, 1):
        ctx = {
            "asset": episode["asset"], "disease": episode["disease"],
            "stage_name": s["stage"], "stage_i": i, "n_stages": len(stages),
            "time_gate": s["time_gate"], "visible_evidence": s["visible_evidence"],
            "history": "; ".join(history) or "(none yet)",
        }
        decision, note = policy.decide(ctx)
        gold = s["gold_action"]
        ok = accepts(gold, decision)
        traj.append({"stage": s["stage"], "decision": decision, "gold": gold,
                     "correct": ok, "time_gate": s["time_gate"], "note": note})
        history.append(f"{s['stage']}={decision}")
    terminal = traj[-1]
    return {
        "asset": episode["asset"], "arc": episode["arc"], "policy": policy.name,
        "trajectory": traj,
        "stage_accuracy": sum(t["correct"] for t in traj) / len(traj),
        "terminal_decision": terminal["decision"],
        "terminal_gold": episode["terminal_gold"],
        "terminal_correct": accepts(episode["terminal_gold"], terminal["decision"]),
    }


# ======================================================================================
# Agentic TOOL-USE variant — the LLM CALLS adapters mid-stage (ReAct loop) instead of
# consuming pre-gathered evidence. This is the prototype tool-use interface.
# ======================================================================================

class Toolbox:
    """Binds the callable adapters. `call(tool, arg)` returns an observation string."""

    def __init__(self, ot, chembl, ema, sfm=None, molprops=None):
        self.ot, self.chembl, self.ema, self.sfm, self.molprops = ot, chembl, ema, sfm, molprops

    def call(self, tool, arg):
        tool = (tool or "").strip().lower()
        arg = (arg or "").strip()
        try:
            if tool == "opentargets_association":
                r = self.ot.target_disease_association(arg)
                return (f"OpenTargets {arg} <-> {self.ot.disease_name}: score={r['score']} "
                        f"found={r['found']} datatypes={r.get('datatypes', {})} {r.get('note', '')}")
            if tool == "chembl_molecule":
                is_id = arg.upper().startswith("CHEMBL")
                return f"ChEMBL molecule {arg}: {self.chembl.molecule(chembl_id=arg if is_id else None, name=None if is_id else arg)}"
            if tool == "chembl_mechanism":
                return f"ChEMBL mechanism {arg}: {self.chembl.mechanism(arg)}"
            if tool == "ctgov_trial":
                return self._ctgov(arg)
            if tool in ("ema_epar", "ema_ledger"):
                r = self.ema.lookup(arg) if hasattr(self.ema, "lookup") else self.ema.event(arg)
                return f"EMA/EPAR {arg}: {r}"
            if tool == "fda_label":
                return self._fda_label(arg)
            if tool in ("boltz2", "boltz_affinity", "sfm_binding"):
                return self.sfm.predict_binding(arg) if getattr(self, "sfm", None) else "(SFM tool not wired)"
            if tool in ("molprops", "druglikeness"):
                return self.molprops.properties(arg) if getattr(self, "molprops", None) else "(molprops tool not wired)"
            return f"(unknown tool '{tool}')"
        except Exception as e:
            return f"(tool error: {e})"

    @staticmethod
    def _fda_label(q):
        for field in ("brand_name", "generic_name"):
            try:
                url = (f"https://api.fda.gov/drug/label.json?search=openfda.{field}:"
                       f"{urllib.parse.quote(q)}&limit=1")
                d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "adds/0.1"}), timeout=25).read())
                r = d["results"][0]
                of = r.get("openfda", {})
                boxed = "boxed_warning" in r
                bw = (r.get("boxed_warning") or [""])[0].replace("\n", " ")[:180] if boxed else ""
                return (f"openFDA label {of.get('brand_name')} ({of.get('generic_name')}) "
                        f"app={of.get('application_number')} BOXED_WARNING={'YES: ' + bw if boxed else 'no'}")
            except Exception:
                continue
        return f"openFDA: no label found for '{q}' (may be investigational/unapproved)"

    @staticmethod
    def _ctgov(nct):
        url = f"https://clinicaltrials.gov/api/v2/studies/{nct}?format=json"
        d = json.loads(urllib.request.urlopen(url, timeout=25).read())
        ps = d.get("protocolSection", {})
        sm = ps.get("statusModule", {})
        prim = (((ps.get("outcomesModule", {}) or {}).get("primaryOutcomes", [{}]) or [{}])[0]).get("measure", "")
        sig = ""
        try:  # expose the primary-endpoint OUTCOME (met/not-met), not just status/title
            from adapters.ctgov_adapter import _significance
            s = _significance(d.get("resultsSection", {}))
            if s.get("significant") is not None:
                sig = (f" PRIMARY_ENDPOINT_MET={s['significant']} (direction={s['direction']})"
                       + (" [MIXED across endpoints]" if s.get("mixed_within") else ""))
        except Exception:
            pass
        return (f"CT.gov {nct}: status={sm.get('overallStatus')} hasResults={d.get('hasResults')} "
                f"whyStopped={sm.get('whyStopped')} primary='{prim[:80]}'{sig}")


TOOLUSE_PROMPT = """You are a drug-development DECISION agent for asset "{asset}" in "{disease}", at pipeline stage {stage}.
Leads you may look up: target={target}, ChEMBL={chembl}, trial NCT(s)={ncts}, asset_key={key}.

Available tools (issue a call to gather evidence for THIS stage):
  CALL opentargets_association <TARGET_SYMBOL>
  CALL chembl_molecule <NAME or CHEMBLID>
  CALL chembl_mechanism <CHEMBLID>
  CALL ctgov_trial <NCT>
  CALL fda_label <BRAND or GENERIC name>        (FDA approval + boxed warnings)
  CALL ema_epar <BRAND or INN>                  (EU status: Authorised/Revoked/Suspended/not-filed)
  CALL molprops <SMILES or drug name>           (RDKit druglikeness: QED / MW / logP / Lipinski — runs locally)
  CALL boltz2 <TARGET|SMILES-or-ligand>         (SFM: predicted binding affinity / structure confidence — needs GPU)

Observations so far:
{observations}

Action meanings: advance=proceed; stop=failed OR HALTED/WITHDRAWN/REVOKED (the
program has ended — includes a safety-driven market withdrawal or regulatory
revocation); defer=insufficient; request_more_evidence=mixed/contradictory;
flag=invalid evidence OR a STILL-APPROVED drug carrying a serious/novel safety
signal (boxed warning/malignancy/mortality). A withdrawn or revoked drug is stop,
not flag.

{instr} Respond with EXACTLY ONE line, no other text:
  CALL <tool> <arg>     (gather more evidence)
  DECIDE <advance|stop|defer|request_more_evidence|flag>"""


def run_stage_tooluse(model, asset, disease, stage, leads, toolbox, max_calls=3):
    """Bounded ReAct loop for one stage: the LLM issues CALLs then DECIDEs."""
    obs, calls_made = [], []
    for step in range(max_calls + 1):
        force = step == max_calls
        prompt = TOOLUSE_PROMPT.format(
            asset=asset, disease=disease, stage=stage,
            target=leads.get("target"), chembl=leads.get("chembl"),
            ncts=leads.get("ncts"), key=leads.get("key"),
            observations="\n".join(obs) or "(none yet)",
            instr="You MUST DECIDE now." if force else "Then CALL a tool OR DECIDE.")
        resp = _claude(prompt, model)
        line = next((l.strip() for l in resp.splitlines()
                     if l.strip().upper().startswith(("CALL", "DECIDE"))), resp.strip())
        if line.upper().startswith("CALL") and not force:
            parts = line.split(None, 2)
            tool = parts[1] if len(parts) > 1 else ""
            targ = parts[2] if len(parts) > 2 else ""
            obs.append(f"[CALL {tool} {targ}] -> {toolbox.call(tool, targ)}")
            calls_made.append(f"{tool}({targ})")
        else:
            action = next((a for a in ACTIONS if a in line.lower()), "defer")
            return {"decision": action, "tool_calls": calls_made, "observations": obs}
    return {"decision": "defer", "tool_calls": calls_made, "observations": obs}
