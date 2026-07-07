"""Tests for the workflow runner — phase advance, gate enforcement, loop policy."""
from __future__ import annotations

import pytest

from agentic import bundle, ledger, run


@pytest.fixture
def proj(tmp_path):
    root = tmp_path / "proj"
    (root / ".agentic" / "ledger").mkdir(parents=True)
    bundle.save(
        str(root),
        {
            "schema_version": "1",
            "name": "t",
            "sdlc": {
                "roles": [{"id": "eng", "capabilities": ["edit"]}],
                "lifecycle": {
                    "phases": ["plan", "implement", "ship"],
                    "gates": {
                        "dor": {"after": "plan", "requires": ["plan_note"]},
                        "dod": {"after": "ship", "requires": ["shipped"]},
                    },
                },
                "loops": {"implement": {"until": "tests_pass", "max_attempts": 2, "on_exhausted": "relay"}},
            },
            "projections": ["claude-code"],
        },
    )
    return str(root)


def test_start_and_list(proj):
    r = run.start(proj, "add feature")
    assert r["phase"] == "plan" and r["status"] == "active"
    assert run.load(proj, r["run_id"])["title"] == "add feature"
    assert len(run.list_runs(proj)) == 1


def test_gate_blocks_until_artifact(proj):
    r = run.start(proj, "x")
    res = run.advance(proj, r["run_id"])            # plan gate needs plan_note
    assert res["blocked"] and "plan_note" in res["missing"]
    run.submit_artifact(proj, r["run_id"], "plan_note")
    res = run.advance(proj, r["run_id"])
    assert res["ok"] and res["phase"] == "implement"


def test_loop_exhaustion_escalates_to_relay(proj):
    r = run.start(proj, "x")
    run.submit_artifact(proj, r["run_id"], "plan_note")
    run.advance(proj, r["run_id"])                  # → implement
    a1 = run.advance(proj, r["run_id"])             # attempt 1: missing tests_pass
    assert a1["blocked"] and a1["status"] == "active"
    a2 = run.advance(proj, r["run_id"])             # attempt 2 == max → escalate
    assert a2["blocked"] and a2["status"] == "awaiting_relay"
    assert any(x["status"] == "pending" for x in ledger.list_relays(proj))
    # supplying the artifact lets it proceed and clears the awaiting_relay state
    run.submit_artifact(proj, r["run_id"], "tests_pass")
    a3 = run.advance(proj, r["run_id"])
    assert a3["ok"] and a3["phase"] == "ship" and a3["status"] == "active"


def test_full_run_to_done(proj):
    r = run.start(proj, "x")
    for art, _ in [("plan_note", 1), ("tests_pass", 1), ("shipped", 1)]:
        run.advance(proj, r["run_id"])              # may block until artifact present
        run.submit_artifact(proj, r["run_id"], art)
        run.advance(proj, r["run_id"])
    final = run.load(proj, r["run_id"])
    assert final["status"] == "done" and final["phase"] == "ship"
    # provenance recorded
    evs = {e["event"] for e in ledger.entries(proj, r["run_id"])}
    assert {"run_started", "phase_advanced", "run_done"} <= evs
