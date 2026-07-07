"""Append-only, hash-chained provenance ledger + relay items (local, git-native)."""
from __future__ import annotations

import json
import os
import time

from .util import chain_hash, ulid

GENESIS = "0" * 64


def _agentic_dir(root: str) -> str:
    return os.path.join(root, ".agentic")


def ledger_path(root: str) -> str:
    return os.path.join(_agentic_dir(root), "ledger", "log.jsonl")


def _sessions_path(root: str) -> str:
    return os.path.join(_agentic_dir(root), "ledger", "sessions.json")


def relay_dir(root: str) -> str:
    return os.path.join(_agentic_dir(root), "relay")


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def run_id_for_session(root: str, session_id: str | None) -> str:
    """Stable run_id per harness session so all events in a run share an id."""
    if not session_id:
        return ulid()
    path = _sessions_path(root)
    sessions = {}
    if os.path.exists(path):
        try:
            sessions = json.load(open(path))
        except Exception:
            sessions = {}
    if session_id not in sessions:
        sessions[session_id] = ulid()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump(sessions, open(path, "w"), indent=2)
    return sessions[session_id]


def _read_entries(root: str):
    path = ledger_path(root)
    if not os.path.exists(path):
        return []
    out = []
    for line in open(path):
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def append(root: str, entry: dict) -> dict:
    """Append an entry, chaining its hash to the previous one."""
    path = ledger_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    entries = _read_entries(root)
    prev = entries[-1]["hash"] if entries else GENESIS
    entry = {"ledger_version": "1", "seq": len(entries), "prev_hash": prev, **entry}
    entry["hash"] = chain_hash(prev, entry)
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def verify(root: str):
    """Return (ok, count, first_bad_seq) verifying the hash chain."""
    prev = GENESIS
    n = 0
    for e in _read_entries(root):
        expect = chain_hash(prev, e)
        if e.get("hash") != expect or e.get("prev_hash") != prev:
            return False, n, e.get("seq")
        prev = e["hash"]
        n += 1
    return True, n, None


def entries(root: str, run_id: str | None = None):
    all_e = _read_entries(root)
    return [e for e in all_e if e.get("run_id") == run_id] if run_id else all_e


# --------------------------------------------------------------- live tail
def since(root: str, seq: int):
    """Return entries whose ``seq >= seq`` (for tailing). [] if the log is empty."""
    return [e for e in _read_entries(root) if e.get("seq", -1) >= seq]


def follow(root: str, printer, poll: float = 0.5) -> None:
    """Live tail: call ``printer(entry)`` for each new entry as it appears.

    Tracks how many entries have been emitted; polls the log every ``poll``
    seconds. Returns cleanly on KeyboardInterrupt and never crashes if the log
    file does not exist yet.
    """
    emitted = 0
    try:
        while True:
            for entry in since(root, emitted):
                printer(entry)
                emitted = entry.get("seq", emitted) + 1
            time.sleep(poll)
    except KeyboardInterrupt:
        return


def gate_log_path(root: str) -> str:
    return os.path.join(_agentic_dir(root), "ledger", "gate.log")


def gate_log(root: str, line: str) -> None:
    """Append a human-readable ``line`` to ``.agentic/ledger/gate.log``."""
    if not line.endswith("\n"):
        line += "\n"
    path = gate_log_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(line)


# --------------------------------------------------------------- relay
def open_relay(root: str, run_id: str, reason: str, subject: dict) -> dict:
    os.makedirs(relay_dir(root), exist_ok=True)
    item = {
        "relay_id": "rel-" + ulid()[-8:],
        "run_id": run_id,
        "status": "pending",
        "reason": reason,
        "subject": subject,
        "created_at": now(),
        "resolution": None,
    }
    json.dump(item, open(os.path.join(relay_dir(root), item["relay_id"] + ".json"), "w"), indent=2)
    return item


def list_relays(root: str):
    d = relay_dir(root)
    if not os.path.isdir(d):
        return []
    out = []
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".json"):
            out.append(json.load(open(os.path.join(d, fn))))
    return out


def resolve_relay(root: str, relay_id: str, decision: str, approver: str, reason: str = "") -> dict | None:
    path = os.path.join(relay_dir(root), relay_id + ".json")
    if not os.path.exists(path):
        return None
    item = json.load(open(path))
    item["status"] = "resolved" if decision in ("approve", "approve_with_edit") else "rejected"
    item["resolution"] = {"resolved_at": now(), "approver": approver, "decision": decision, "reason": reason}
    json.dump(item, open(path, "w"), indent=2)
    append(
        root,
        {
            "run_id": item["run_id"],
            "altitude": "sdlc",
            "event": "relay_resolved",
            "subject": item["subject"],
            "decision": decision,
            "reason": f"{approver}: {reason}".strip(": "),
            "ts": now(),
        },
    )
    return item
