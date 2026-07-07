"""Tests for `agentic deliver` — worktree isolation, collision scheduling, merge."""
from __future__ import annotations

import os
import subprocess

import pytest

from agentic import bundle, deliver, run


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(["init", "-q", "-b", "main"], root)
    # repo-local identity so deliver's internal `git merge` works even where
    # there's no global git config (e.g. CI runners)
    _git(["config", "user.name", "Test"], root)
    _git(["config", "user.email", "test@example.com"], root)
    (root / ".agentic").mkdir()
    bundle.save(
        str(root),
        {
            "schema_version": "1",
            "name": "r",
            "sdlc": {
                "roles": [{"id": "eng", "capabilities": ["edit"]}],
                "lifecycle": {
                    "phases": ["plan", "ship"],
                    "gates": {"dor": {"after": "plan", "requires": ["plan_note"]}},
                },
            },
            "projections": ["claude-code"],
        },
    )
    (root / "README.md").write_text("base\n")
    _git(["add", "-A"], root)
    _git(["-c", "user.name=T", "-c", "user.email=t@t", "commit", "-qm", "init"], root)
    return str(root)


def test_start_creates_worktrees_and_branches(repo):
    epic = deliver.start(repo, [{"title": "a", "paths": ["src/a/**"]}, {"title": "b", "paths": ["src/b/**"]}])
    assert len(epic["items"]) == 2
    for it in epic["items"]:
        assert os.path.isdir(it["worktree"])
        branches = subprocess.run(["git", "-C", repo, "branch", "--list", it["branch"]],
                                  capture_output=True, text=True).stdout
        assert it["branch"] in branches


def test_schedule_parallel_vs_serial(repo):
    e1 = deliver.start(repo, [{"title": "a", "paths": ["src/a/**"]}, {"title": "b", "paths": ["src/b/**"]}])
    assert len(deliver.schedule(repo, e1["epic_id"])) == 1          # disjoint → one parallel batch
    e2 = deliver.start(repo, [{"title": "c", "paths": ["src/x/**"]}, {"title": "d", "paths": ["src/x/**"]}])
    assert len(deliver.schedule(repo, e2["epic_id"])) == 2          # same path → serialized


def test_merge_requires_done_then_lands_on_base(repo):
    epic = deliver.start(repo, [{"title": "feat", "paths": ["src/a/**"]}])
    it = epic["items"][0]
    rid = it["run_id"]

    # a commit on the item's branch (in its worktree)
    (os.path.join(it["worktree"], "feature.txt"))
    open(os.path.join(it["worktree"], "feature.txt"), "w").write("x\n")
    _git(["add", "-A"], it["worktree"])
    _git(["-c", "user.name=T", "-c", "user.email=t@t", "commit", "-qm", "feat"], it["worktree"])

    # merge is refused until the run is done
    assert deliver.merge(repo, rid)["ok"] is False

    # drive the run to done: plan (needs plan_note) → ship → done
    run.advance(repo, rid)
    run.submit_artifact(repo, rid, "plan_note")
    run.advance(repo, rid)   # → ship
    run.advance(repo, rid)   # ship is last → done
    assert run.load(repo, rid)["status"] == "done"

    res = deliver.merge(repo, rid)
    assert res["ok"]
    assert os.path.exists(os.path.join(repo, "feature.txt"))        # landed on base
    assert not os.path.isdir(it["worktree"])                        # worktree cleaned up
