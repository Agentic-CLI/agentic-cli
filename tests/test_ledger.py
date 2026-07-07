"""Tests for agentic.ledger — the append-only, hash-chained provenance log
plus relay (human-in-the-loop) items."""
import json

from agentic import ledger


def _read_lines(root):
    with open(ledger.ledger_path(root)) as f:
        return [json.loads(line) for line in f if line.strip()]


def _rewrite_lines(root, entries):
    with open(ledger.ledger_path(root), "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


# --------------------------------------------------------------- append/verify
def test_append_builds_valid_chain(tmp_path):
    root = str(tmp_path)
    for i in range(3):
        ledger.append(root, {"event": "pre_tool", "n": i})
    ok, count, first_bad = ledger.verify(root)
    assert ok is True
    assert count == 3
    assert first_bad is None


def test_append_populates_seq_prev_and_hash(tmp_path):
    root = str(tmp_path)
    e0 = ledger.append(root, {"event": "a"})
    e1 = ledger.append(root, {"event": "b"})
    assert e0["seq"] == 0
    assert e0["prev_hash"] == ledger.GENESIS
    assert e0["ledger_version"] == "1"
    assert e1["seq"] == 1
    assert e1["prev_hash"] == e0["hash"]
    assert e1["hash"] != e0["hash"]


def test_verify_empty_ledger_is_ok(tmp_path):
    ok, count, first_bad = ledger.verify(str(tmp_path))
    assert ok is True
    assert count == 0
    assert first_bad is None


def test_tampering_with_a_field_is_detected_at_the_right_seq(tmp_path):
    """Crown jewel: rewrite a stored field but leave the stale hash → verify must
    fail exactly at the tampered entry's seq."""
    root = str(tmp_path)
    for i in range(4):
        ledger.append(root, {"event": "pre_tool", "tool": "Edit", "n": i})

    entries = _read_lines(root)
    # Tamper the middle entry (seq 2): change a field, leave its stored hash stale.
    entries[2]["tool"] = "Write"
    _rewrite_lines(root, entries)

    ok, count, first_bad = ledger.verify(root)
    assert ok is False
    assert first_bad == 2
    assert count == 2  # entries 0 and 1 verified before the break


def test_tampering_with_stored_hash_is_detected(tmp_path):
    root = str(tmp_path)
    ledger.append(root, {"event": "a"})
    ledger.append(root, {"event": "b"})
    entries = _read_lines(root)
    entries[1]["hash"] = "0" * 64
    _rewrite_lines(root, entries)
    ok, _, first_bad = ledger.verify(root)
    assert ok is False
    assert first_bad == 1


def test_entries_filtered_by_run_id(tmp_path):
    root = str(tmp_path)
    ledger.append(root, {"run_id": "R1", "event": "a"})
    ledger.append(root, {"run_id": "R2", "event": "b"})
    ledger.append(root, {"run_id": "R1", "event": "c"})
    r1 = ledger.entries(root, "R1")
    assert [e["event"] for e in r1] == ["a", "c"]
    assert len(ledger.entries(root)) == 3


# --------------------------------------------------------------- run_id
def test_run_id_stable_per_session(tmp_path):
    root = str(tmp_path)
    rid1 = ledger.run_id_for_session(root, "sess-abc")
    rid2 = ledger.run_id_for_session(root, "sess-abc")
    assert rid1 == rid2


def test_run_id_differs_across_sessions(tmp_path):
    root = str(tmp_path)
    assert ledger.run_id_for_session(root, "s1") != ledger.run_id_for_session(root, "s2")


def test_run_id_without_session_is_random(tmp_path):
    root = str(tmp_path)
    assert ledger.run_id_for_session(root, None) != ledger.run_id_for_session(root, None)


# --------------------------------------------------------------- relay
def test_open_and_list_relay(tmp_path):
    root = str(tmp_path)
    item = ledger.open_relay(root, "run-1", "needs review", {"type": "file", "ref": "x.py"})
    assert item["status"] == "pending"
    assert item["relay_id"].startswith("rel-")
    assert item["resolution"] is None
    listed = ledger.list_relays(root)
    assert len(listed) == 1
    assert listed[0]["relay_id"] == item["relay_id"]


def test_list_relays_empty_when_no_dir(tmp_path):
    assert ledger.list_relays(str(tmp_path)) == []


def test_resolve_relay_approve_flow(tmp_path):
    root = str(tmp_path)
    item = ledger.open_relay(root, "run-1", "review", {"type": "file", "ref": "m.py"})
    resolved = ledger.resolve_relay(root, item["relay_id"], "approve", "dev@payme.ws", "looks good")
    assert resolved is not None
    assert resolved["status"] == "resolved"
    assert resolved["resolution"]["decision"] == "approve"
    assert resolved["resolution"]["approver"] == "dev@payme.ws"
    # Resolving also appends an audit entry to the chained ledger.
    ok, count, _ = ledger.verify(root)
    assert ok is True
    assert count == 1
    assert ledger.entries(root)[0]["event"] == "relay_resolved"


def test_resolve_relay_reject_sets_rejected_status(tmp_path):
    root = str(tmp_path)
    item = ledger.open_relay(root, "run-1", "review", {"type": "file", "ref": "m.py"})
    resolved = ledger.resolve_relay(root, item["relay_id"], "reject", "dev@payme.ws")
    assert resolved["status"] == "rejected"


def test_resolve_relay_open_then_resolve_persists_to_disk(tmp_path):
    root = str(tmp_path)
    item = ledger.open_relay(root, "run-9", "review", {"type": "file", "ref": "m.py"})
    ledger.resolve_relay(root, item["relay_id"], "approve", "dev@payme.ws", "ok")
    reloaded = ledger.list_relays(root)[0]
    assert reloaded["status"] == "resolved"
    assert reloaded["resolution"]["reason"] == "ok"


def test_resolve_missing_relay_returns_none(tmp_path):
    assert ledger.resolve_relay(str(tmp_path), "rel-NOPE", "approve", "x") is None
