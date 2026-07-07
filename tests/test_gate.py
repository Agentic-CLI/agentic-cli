"""Tests for agentic.gate — the Claude Code PreToolUse hook handler.

The gate reads a hook event as JSON on stdin, resolves the project root from the
event's ``cwd``, records the action to the ledger, and blocks (exit 2) sensitive
paths that require a human relay while allowing (exit 0) everything else.
"""
import io
import json

from agentic import bundle, gate, ledger


def _make_project(tmp_path):
    """A real agentic project on disk: a saved default bundle (so .agentic/
    exists and find_project_root resolves) rooted at tmp_path."""
    root = str(tmp_path)
    bundle.save(root, bundle.default("gate-proj"))
    return root


def _run_gate(monkeypatch, event):
    monkeypatch.setattr(gate.sys, "stdin", io.StringIO(json.dumps(event)))
    return gate.run([])


# --------------------------------------------------------------- sensitive
def test_blocks_sensitive_path_requiring_human_relay(tmp_path, monkeypatch):
    root = _make_project(tmp_path)
    event = {
        "cwd": root,
        "session_id": "sess-1",
        "tool_name": "Write",
        "tool_input": {"file_path": "src/todo/models/todo.py"},
    }
    rc = _run_gate(monkeypatch, event)
    assert rc == 2

    # A ledger entry was recorded as a block, and the chain stays valid.
    entries = ledger.entries(root)
    assert len(entries) == 1
    assert entries[0]["decision"] == "block"
    assert entries[0]["sensitivity"] == "sensitive"
    assert entries[0]["subject"] == {"type": "file", "ref": "src/todo/models/todo.py"}
    ok, _, _ = ledger.verify(root)
    assert ok is True

    # A pending relay item was opened.
    relays = ledger.list_relays(root)
    assert len(relays) == 1
    assert relays[0]["status"] == "pending"
    assert "human_relay" in relays[0]["reason"]


# ------------------------------------------------------------------ allow
def test_allows_normal_path(tmp_path, monkeypatch):
    root = _make_project(tmp_path)
    event = {
        "cwd": root,
        "session_id": "sess-1",
        "tool_name": "Edit",
        "tool_input": {"file_path": "src/todo/api.py"},
    }
    rc = _run_gate(monkeypatch, event)
    assert rc == 0

    entries = ledger.entries(root)
    assert len(entries) == 1
    assert entries[0]["decision"] == "allow"
    assert entries[0]["sensitivity"] == "normal"
    # No relay opened on the allow path.
    assert ledger.list_relays(root) == []


def test_allows_non_file_tool(tmp_path, monkeypatch):
    root = _make_project(tmp_path)
    event = {"cwd": root, "session_id": "s", "tool_name": "Bash", "tool_input": {"command": "ls"}}
    rc = _run_gate(monkeypatch, event)
    assert rc == 0
    entry = ledger.entries(root)[0]
    assert entry["decision"] == "allow"
    assert entry["subject"] == {"type": "tool", "ref": "Bash"}


# ------------------------------------------------------------- edge cases
def test_returns_zero_outside_agentic_project(tmp_path, monkeypatch):
    """No .agentic dir anywhere → stay out of the way, record nothing."""
    plain = tmp_path / "plain"
    plain.mkdir()
    event = {"cwd": str(plain), "tool_name": "Write", "tool_input": {"file_path": "x.py"}}
    # Point cwd resolution and the fallback both at a non-project dir.
    monkeypatch.chdir(plain)
    rc = _run_gate(monkeypatch, event)
    assert rc == 0


def test_records_stable_run_id_across_events_in_a_session(tmp_path, monkeypatch):
    root = _make_project(tmp_path)
    base = {"cwd": root, "session_id": "same-session", "tool_name": "Edit"}
    _run_gate(monkeypatch, {**base, "tool_input": {"file_path": "src/a.py"}})
    _run_gate(monkeypatch, {**base, "tool_input": {"file_path": "src/b.py"}})
    run_ids = {e["run_id"] for e in ledger.entries(root)}
    assert len(run_ids) == 1  # same session → one stable run_id


def test_empty_stdin_returns_zero(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # not an agentic project
    monkeypatch.setattr(gate.sys, "stdin", io.StringIO(""))
    assert gate.run([]) == 0
