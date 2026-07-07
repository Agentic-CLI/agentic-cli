"""agentic deliver — drive an EPIC (many work-items) through the lifecycle in
isolated git worktrees, with collision-aware scheduling and a conflict-aware,
sequential merge queue.

Each item gets its own run (run.py) and its own git worktree + branch, so
disjoint items can proceed in parallel and file-colliding items are serialized.
The CLI conducts, isolates, and records; the harness runs the agent inside each
worktree. State lives in ``.agentic/deliver/<epic_id>.json``; worktrees under
``.agentic/wt/<run_id>``.
"""
from __future__ import annotations

import json
import os
import subprocess

from . import ledger, run
from .util import glob_match, ulid


def _deliver_dir(root: str) -> str:
    return os.path.join(root, ".agentic", "deliver")


def _epic_path(root: str, epic_id: str) -> str:
    return os.path.join(_deliver_dir(root), f"{epic_id}.json")


def _wt_dir(root: str) -> str:
    return os.path.join(root, ".agentic", "wt")


def _git(root: str, args, cwd=None):
    return subprocess.run(["git", "-C", cwd or root, *args], capture_output=True, text=True)


def _require_git(root: str) -> None:
    if _git(root, ["rev-parse", "--is-inside-work-tree"]).returncode != 0:
        raise RuntimeError("not a git repository — `agentic deliver` needs git worktrees")


def _current_branch(root: str) -> str:
    return _git(root, ["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()


def _save(root: str, epic: dict) -> dict:
    os.makedirs(_deliver_dir(root), exist_ok=True)
    with open(_epic_path(root, epic["epic_id"]), "w") as f:
        json.dump(epic, f, indent=2)
    return epic


def load(root: str, epic_id: str) -> dict | None:
    p = _epic_path(root, epic_id)
    return json.load(open(p)) if os.path.exists(p) else None


def list_epics(root: str) -> list:
    d = _deliver_dir(root)
    if not os.path.isdir(d):
        return []
    return [json.load(open(os.path.join(d, f))) for f in sorted(os.listdir(d)) if f.endswith(".json")]


def _norm_item(it) -> dict:
    if isinstance(it, str):
        return {"title": it, "paths": []}
    return {"title": it.get("title", "untitled"), "paths": it.get("paths") or []}


def start(root: str, items: list) -> dict:
    """Create a run + isolated git worktree/branch for each item in the epic."""
    _require_git(root)
    base = _current_branch(root)
    epic_id = ulid()
    os.makedirs(_wt_dir(root), exist_ok=True)
    entries = []
    for raw in items:
        it = _norm_item(raw)
        r = run.start(root, it["title"])
        branch = f"agentic/{r['run_id'][-8:]}"
        wt = os.path.join(_wt_dir(root), r["run_id"])
        res = _git(root, ["worktree", "add", "-b", branch, wt, base])
        if res.returncode != 0:
            raise RuntimeError(f"git worktree add failed for '{it['title']}': {res.stderr.strip()}")
        entries.append({"run_id": r["run_id"], "title": it["title"], "paths": it["paths"],
                        "branch": branch, "worktree": wt, "merged": False})
    epic = {"epic_id": epic_id, "base_branch": base, "created_at": ledger.now(), "items": entries}
    _save(root, epic)
    ledger.append(root, {"run_id": epic_id, "altitude": "sdlc", "event": "deliver_started",
                         "subject": {"type": "epic", "ref": f"{len(entries)} items"},
                         "decision": "started", "reason": base, "ts": ledger.now()})
    return epic


def _collide(a_paths, b_paths) -> bool:
    """Two items collide if their path globs overlap, or either declares no paths
    (unknown blast radius → conservatively serialize)."""
    if not a_paths or not b_paths:
        return True
    for pa in a_paths:
        for pb in b_paths:
            if pa == pb or glob_match(pa, pb.rstrip("*/")) or glob_match(pb, pa.rstrip("*/")):
                return True
            ta, tb = pa.split("*")[0].rstrip("/"), pb.split("*")[0].rstrip("/")
            if ta and tb and (ta == tb or ta.startswith(tb + "/") or tb.startswith(ta + "/")):
                return True
    return False


def schedule(root: str, epic_id: str) -> list:
    """Greedy batching: each batch holds mutually non-colliding items (safe to run
    in parallel); colliding items fall into later batches (serialized)."""
    epic = load(root, epic_id)
    if not epic:
        raise ValueError(f"no such epic: {epic_id}")
    batches: list = []
    for it in [i for i in epic["items"] if not i["merged"]]:
        for batch in batches:
            if all(not _collide(it["paths"], o["paths"]) for o in batch):
                batch.append(it)
                break
        else:
            batches.append([it])
    return batches


def merge(root: str, run_id: str) -> dict:
    """Merge a completed item's branch into base (conflict-aware). On success,
    remove the worktree + branch. The item's run must be ``done``."""
    for epic in list_epics(root):
        for it in epic["items"]:
            if it["run_id"].startswith(run_id) and not it["merged"]:
                r = run.load(root, it["run_id"])
                if not r or r["status"] != "done":
                    return {"ok": False, "reason": f"run not complete (status: {r['status'] if r else 'missing'})"}
                res = _git(root, ["merge", "--no-ff", "-m", f"deliver: {it['title']}", it["branch"]])
                if res.returncode != 0:
                    _git(root, ["merge", "--abort"])
                    ledger.append(root, {"run_id": it["run_id"], "altitude": "sdlc", "event": "merge_conflict",
                                         "subject": {"type": "branch", "ref": it["branch"]},
                                         "decision": "block", "reason": "conflict", "ts": ledger.now()})
                    return {"ok": False, "reason": f"merge conflict on {it['branch']} — resolve manually"}
                _git(root, ["worktree", "remove", "--force", it["worktree"]])
                _git(root, ["branch", "-D", it["branch"]])
                it["merged"] = True
                _save(root, epic)
                ledger.append(root, {"run_id": it["run_id"], "altitude": "sdlc", "event": "merged",
                                     "subject": {"type": "branch", "ref": it["branch"]},
                                     "decision": "merged", "reason": epic["base_branch"], "ts": ledger.now()})
                return {"ok": True, "branch": it["branch"], "base": epic["base_branch"]}
    return {"ok": False, "reason": f"no unmerged item matching '{run_id}'"}
