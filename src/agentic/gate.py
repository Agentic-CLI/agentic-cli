"""The Supervise step: a Claude Code PreToolUse hook handler.

Reads the hook event JSON on stdin, records the action to the provenance
ledger (Observe — always), and — for paths the bundle marks sensitive that
require a human relay — blocks the tool call and opens a relay item (Govern).

Non-invasive by construction: it only runs at the harness's own hook boundary,
enforces solely at declared gates, and records everything else without blocking.
"""
from __future__ import annotations

import json
import sys

from . import bundle, ledger
from .util import find_project_root, glob_match


def _extract(event: dict):
    tool = event.get("tool_name") or event.get("tool") or ""
    ti = event.get("tool_input") or {}
    path = ti.get("file_path") or ti.get("path") or ti.get("notebook_path")
    return tool, path, event.get("session_id")


def _match_sensitivity(data: dict, path: str):
    for rule in data.get("sdlc", {}).get("sensitivity", {}).get("rules", []):
        for pat in rule.get("match", {}).get("paths", []):
            if glob_match(pat, path):
                return rule
    return None


def run(argv) -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except Exception:
        event = {}

    root = event.get("cwd") and find_project_root(event["cwd"]) or find_project_root()
    if not root:
        return 0  # not an agentic project — stay out of the way

    tool, path, session_id = _extract(event)
    try:
        data = bundle.load(root)
    except Exception:
        return 0

    run_id = ledger.run_id_for_session(root, session_id)
    rule = _match_sensitivity(data, path) if path else None
    sensitive = bool(rule)
    require = rule.get("require", []) if rule else []
    blocking = sensitive and "human_relay" in require

    entry = {
        "run_id": run_id,
        "altitude": "sdlc",
        "event": "pre_tool",
        "tool": tool,
        "subject": {"type": "file", "ref": path} if path else {"type": "tool", "ref": tool},
        "sensitivity": rule.get("level") if rule else "normal",
        "decision": "block" if blocking else "allow",
        "reason": "sensitive path requires human relay" if blocking else "",
        "ts": ledger.now(),
    }
    ledger.append(root, entry)
    ledger.gate_log(
        root,
        f"{entry['ts']}  {entry['decision']:<5} "
        f"{entry.get('sensitivity', 'normal'):<9} {tool} {path or ''}",
    )

    if blocking:
        item = ledger.open_relay(
            root, run_id, f"{tool} on sensitive path {path} (requires: {', '.join(require)})",
            entry["subject"],
        )
        msg = (
            f"[agentic] BLOCKED: {tool} on '{path}' is a sensitive change.\n"
            f"Required before it can proceed: {', '.join(require)}.\n"
            f"Relay opened: {item['relay_id']} (run {run_id[:8]}).\n"
            f"A human must approve:  agentic relay resolve {item['relay_id']} --approve"
        )
        print(msg, file=sys.stderr)
        return 2  # Claude Code: exit 2 blocks the tool call and feeds stderr back

    return 0
