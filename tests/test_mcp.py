"""Tests for agentic.mcp — the MCP stdio JSON-RPC 2.0 server.

Everything is driven through the pure core :func:`mcp.dispatch`, so no real
stdio is involved. ``tests/conftest.py`` already puts ``src/`` on ``sys.path``.
"""
import json

from agentic import bundle, ledger, mcp


def _make_project(root):
    """A bundle with one sensitivity rule and one standards entry."""
    data = bundle.default("demo")
    # A deterministic, single sensitivity rule for the test.
    data["sdlc"]["sensitivity"] = {
        "rules": [
            {
                "match": {"paths": ["src/auth/**", "**/*secret*"]},
                "level": "sensitive",
                "require": ["adversarial_review", "human_relay"],
            }
        ]
    }
    data["sdlc"]["standards"] = [
        {
            "id": "money-truth",
            "title": "Money Truth",
            "rules": ["Never lose a transaction", "Reconcile to the ledger"],
        }
    ]
    bundle.save(root, data)
    return data


def _text(resp):
    """Extract the decoded tools/call text payload from a response."""
    content = resp["result"]["content"]
    return json.loads(content[0]["text"])


# ─────────────────────────────────────────────────────────── protocol
def test_initialize(tmp_path):
    root = str(tmp_path)
    resp = mcp.dispatch(root, "initialize", {}, 1)
    assert resp["id"] == 1
    result = resp["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert result["serverInfo"]["name"] == "agentic"
    assert "version" in result["serverInfo"]
    assert "tools" in result["capabilities"]


def test_notifications_initialized_no_response(tmp_path):
    resp = mcp.dispatch(str(tmp_path), "notifications/initialized", None, None)
    assert resp is None


def test_unknown_method_errors(tmp_path):
    resp = mcp.dispatch(str(tmp_path), "does/not/exist", {}, 7)
    assert resp["error"]["code"] == -32601


def test_tools_list(tmp_path):
    resp = mcp.dispatch(str(tmp_path), "tools/list", {}, 2)
    tools = resp["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {"check_path", "get_standards", "record"} <= names
    for t in tools:
        assert "description" in t
        schema = t["inputSchema"]
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema


# ─────────────────────────────────────────────────────────── tools/call
def _call(root, name, arguments, msg_id=10):
    return mcp.dispatch(root, "tools/call", {"name": name, "arguments": arguments}, msg_id)


def test_check_path_sensitive(tmp_path):
    root = str(tmp_path)
    _make_project(root)
    resp = _call(root, "check_path", {"path": "src/auth/login.py"})
    assert resp["result"]["isError"] is False
    data = _text(resp)
    assert data["sensitive"] is True
    assert data["level"] == "sensitive"
    assert "human_relay" in data["require"]


def test_check_path_not_sensitive(tmp_path):
    root = str(tmp_path)
    _make_project(root)
    resp = _call(root, "check_path", {"path": "src/util/format.py"})
    data = _text(resp)
    assert data["sensitive"] is False
    assert data["require"] == []


def test_get_standards(tmp_path):
    root = str(tmp_path)
    _make_project(root)
    resp = _call(root, "get_standards", {})
    stds = _text(resp)
    assert any(s["id"] == "money-truth" for s in stds)


def test_record_appends_to_ledger(tmp_path):
    root = str(tmp_path)
    _make_project(root)
    resp = _call(root, "record", {"event": "decision", "subject": "x", "reason": "because"})
    assert resp["result"]["isError"] is False
    data = _text(resp)
    assert "hash" in data

    entries = ledger.entries(root)
    assert len(entries) == 1
    assert entries[0]["event"] == "decision"
    assert entries[0]["hash"] == data["hash"]


def test_unknown_tool_is_error(tmp_path):
    root = str(tmp_path)
    _make_project(root)
    resp = _call(root, "no_such_tool", {})
    assert resp["result"]["isError"] is True
