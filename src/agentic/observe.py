"""Observe mode: reconstruct provenance from artifacts that already exist.

POC scope: ingest recent git history into the ledger so a cold repo gets a
day-1 provenance record with zero behavior change. Real adapters (PR reviews,
harness session logs, CI results) plug in here later.
"""
from __future__ import annotations

import subprocess

from . import ledger


def from_git(root: str, since: str = "30 days ago") -> int:
    try:
        out = subprocess.run(
            ["git", "-C", root, "log", f"--since={since}", "--pretty=%H%x1f%an%x1f%aI%x1f%s"],
            capture_output=True, text=True, check=True,
        ).stdout
    except Exception:
        return 0
    seen = {e.get("subject", {}).get("ref") for e in ledger.entries(root) if e.get("event") == "commit"}
    n = 0
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) != 4:
            continue
        sha, author, iso, subject = parts
        if sha in seen:
            continue
        ledger.append(
            root,
            {
                "run_id": "git-" + sha[:10],
                "altitude": "sdlc",
                "event": "commit",
                "subject": {"type": "commit", "ref": sha, "message": subject},
                "actor": author,
                "decision": "observed",
                "reason": "",
                "ts": iso,
            },
        )
        n += 1
    return n
