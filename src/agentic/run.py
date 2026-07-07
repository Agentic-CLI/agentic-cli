"""Workflow runner — drive one unit of work through the lifecycle.

The CLI *conducts and records*; the harness (Claude Code / Cursor) *executes* each
phase. A run walks the declared lifecycle phase by phase; advancing is blocked
until the phase's gate artifacts exist, loop policy bounds retries, and an
exhausted loop escalates to a human relay. Every transition is recorded in the
trust ledger.

State lives in ``.agentic/runs/<run_id>.json``. Requirements to leave a phase P:
- the gate declared ``after: P`` (``requires: [...]``), plus
- that phase's loop ``until`` artifact, if a ``loops.<P>`` policy is set.
"""
from __future__ import annotations

import json
import os

from . import ledger, resolve
from .util import ulid


def _runs_dir(root: str) -> str:
    return os.path.join(root, ".agentic", "runs")


def _run_path(root: str, run_id: str) -> str:
    return os.path.join(_runs_dir(root), f"{run_id}.json")


def _save(root: str, run: dict) -> dict:
    os.makedirs(_runs_dir(root), exist_ok=True)
    run["updated_at"] = ledger.now()
    with open(_run_path(root, run["run_id"]), "w") as f:
        json.dump(run, f, indent=2)
    return run


def load(root: str, run_id: str) -> dict | None:
    p = _run_path(root, run_id)
    if not os.path.exists(p):
        return None
    return json.load(open(p))


def list_runs(root: str) -> list:
    d = _runs_dir(root)
    if not os.path.isdir(d):
        return []
    out = []
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".json"):
            out.append(json.load(open(os.path.join(d, fn))))
    return out


def _lifecycle(root: str):
    data = resolve.effective_bundle(root)
    lc = data.get("sdlc", {}).get("lifecycle", {})
    phases = lc.get("phases", [])
    gates = lc.get("gates", {})
    loops = data.get("sdlc", {}).get("loops", {})
    return phases, gates, loops


def start(root: str, title: str) -> dict:
    phases, _gates, _loops = _lifecycle(root)
    if not phases:
        raise ValueError("bundle has no sdlc.lifecycle.phases")
    run = {
        "run_id": ulid(),
        "title": title,
        "phase": phases[0],
        "phase_index": 0,
        "status": "active",
        "artifacts": {},
        "attempts": {},
        "created_at": ledger.now(),
    }
    _save(root, run)
    ledger.append(
        root,
        {"run_id": run["run_id"], "altitude": "sdlc", "event": "run_started",
         "subject": {"type": "run", "ref": title}, "decision": "started",
         "reason": "", "ts": ledger.now()},
    )
    return run


def submit_artifact(root: str, run_id: str, name: str, ref: str | None = None) -> dict:
    run = load(root, run_id)
    if run is None:
        raise ValueError(f"no such run: {run_id}")
    run["artifacts"][name] = {"ref": ref, "ts": ledger.now()}
    _save(root, run)
    ledger.append(
        root,
        {"run_id": run_id, "altitude": "sdlc", "event": "artifact",
         "subject": {"type": "artifact", "ref": name}, "decision": "recorded",
         "reason": run["phase"], "ts": ledger.now()},
    )
    return run


def _requirements(cur: str, gates: dict, loops: dict):
    """Artifacts required to leave phase `cur`: its gate + its loop `until`."""
    req, gate_name = [], None
    for gname, g in gates.items():
        if g.get("after") == cur:
            req += list(g.get("requires", []))
            gate_name = gname
    loop = loops.get(cur) or {}
    if loop.get("until"):
        req.append(loop["until"])
    return req, gate_name, loop


def advance(root: str, run_id: str) -> dict:
    """Attempt to move the run to the next phase. Returns a result dict."""
    run = load(root, run_id)
    if run is None:
        return {"run_id": run_id, "ok": False, "blocked": True, "reason": "no such run"}
    if run["status"] == "done":
        return {"run_id": run_id, "ok": False, "blocked": False,
                "reason": "run already complete", "status": "done", "phase": run["phase"]}

    phases, gates, loops = _lifecycle(root)
    cur = run["phase"]
    idx = run["phase_index"]
    req, gate_name, loop = _requirements(cur, gates, loops)
    missing = [r for r in req if r not in run["artifacts"]]

    if missing:
        max_attempts = loop.get("max_attempts")
        run["attempts"][cur] = run["attempts"].get(cur, 0) + 1
        attempt = run["attempts"][cur]
        # loop exhausted → escalate to a human relay
        if max_attempts and attempt >= max_attempts and loop.get("on_exhausted") == "relay":
            item = ledger.open_relay(
                root, run_id,
                f"phase '{cur}' exhausted {attempt}/{max_attempts} attempts; missing {', '.join(missing)}",
                {"type": "run", "ref": run["title"]},
            )
            run["status"] = "awaiting_relay"
            _save(root, run)
            ledger.append(root, {"run_id": run_id, "altitude": "sdlc", "event": "gate_blocked",
                                 "subject": {"type": "phase", "ref": cur}, "decision": "escalated",
                                 "reason": f"relay {item['relay_id']}", "ts": ledger.now()})
            return {"run_id": run_id, "ok": False, "blocked": True, "status": "awaiting_relay",
                    "phase": cur, "reason": f"escalated to human — relay {item['relay_id']}",
                    "missing": missing}
        _save(root, run)
        ledger.append(root, {"run_id": run_id, "altitude": "sdlc", "event": "gate_blocked",
                             "subject": {"type": "phase", "ref": cur}, "decision": "block",
                             "reason": f"missing {', '.join(missing)}", "ts": ledger.now()})
        note = f" (attempt {attempt}/{max_attempts})" if max_attempts else ""
        return {"run_id": run_id, "ok": False, "blocked": True, "status": "active",
                "phase": cur, "gate": gate_name, "missing": missing,
                "reason": f"gate not satisfied — missing: {', '.join(missing)}{note}"}

    # gate satisfied → advance (or complete)
    if idx >= len(phases) - 1:
        run["status"] = "done"
        _save(root, run)
        ledger.append(root, {"run_id": run_id, "altitude": "sdlc", "event": "run_done",
                             "subject": {"type": "run", "ref": run["title"]}, "decision": "done",
                             "reason": "", "ts": ledger.now()})
        return {"run_id": run_id, "ok": True, "blocked": False, "status": "done", "phase": cur}

    nxt = phases[idx + 1]
    run["phase"], run["phase_index"] = nxt, idx + 1
    run["attempts"][nxt] = 0
    run["status"] = "active"
    _save(root, run)
    ledger.append(root, {"run_id": run_id, "altitude": "sdlc", "event": "phase_advanced",
                         "subject": {"type": "phase", "ref": nxt}, "decision": "advance",
                         "reason": f"{cur} → {nxt}" + (f" via {gate_name}" if gate_name else ""),
                         "ts": ledger.now()})
    return {"run_id": run_id, "ok": True, "blocked": False, "status": "active",
            "phase": nxt, "from": cur, "gate": gate_name}
