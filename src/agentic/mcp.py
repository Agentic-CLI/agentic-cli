"""MCP (Model Context Protocol) stdio JSON-RPC 2.0 server for agentic.

Speaks newline-delimited JSON-RPC 2.0 over stdin/stdout (no Content-Length
headers), so any MCP client (Claude Code, Cursor, ...) can drive agentic: check
whether a path is sensitive, read the SDLC standards, append to the provenance
ledger, open a human relay, and (once ``run.py`` lands) inspect / advance runs.

The pure core is :func:`dispatch`, which turns a decoded request into a response
dict without touching real stdio — that's what the tests exercise. :func:`serve`
is the thin I/O loop around it.
"""
from __future__ import annotations

import json
import sys

from . import __version__, ledger, resolve, util

PROTOCOL_VERSION = "2024-11-05"

# JSON-RPC error codes
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603


# ─────────────────────────────────────────────────────────── tool registry
TOOLS = [
    {
        "name": "check_path",
        "description": "Check whether a repo-relative path is sensitive per the "
        "bundle's sdlc.sensitivity rules. Returns the level and required controls.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Repo-relative path to classify."}
            },
            "required": ["path"],
        },
    },
    {
        "name": "get_standards",
        "description": "Return the SDLC standards (id/title/rules) from the effective bundle.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "record",
        "description": "Append an event to the append-only, hash-chained provenance ledger. "
        "Returns the new entry's hash.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "event": {"type": "string", "description": "Event name, e.g. 'decision'."},
                "subject": {"type": "string", "description": "What the event is about."},
                "decision": {"type": "string", "description": "Decision taken, if any."},
                "reason": {"type": "string", "description": "Why."},
            },
            "required": ["event"],
        },
    },
    {
        "name": "open_relay",
        "description": "Open a human-in-the-loop relay item requesting a decision. "
        "Returns the relay_id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why a human is needed."},
                "run_id": {"type": "string", "description": "Run this relay belongs to."},
            },
            "required": ["reason"],
        },
    },
    {
        "name": "run_status",
        "description": "Get one run (run_id given) or list all runs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "Run to load; omit to list all."}
            },
            "required": [],
        },
    },
    {
        "name": "submit_artifact",
        "description": "Submit an artifact to a run for the current lifecycle phase.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "name": {"type": "string", "description": "Artifact name."},
                "ref": {"type": "string", "description": "Optional reference (path/url)."},
            },
            "required": ["run_id", "name"],
        },
    },
    {
        "name": "advance_run",
        "description": "Advance a run to the next lifecycle phase (gates permitting).",
        "inputSchema": {
            "type": "object",
            "properties": {"run_id": {"type": "string"}},
            "required": ["run_id"],
        },
    },
]


# ─────────────────────────────────────────────────────────── response helpers
def _result(msg_id, result):
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id, code, message):
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _content(text, is_error=False):
    """A tools/call result: text content + isError flag."""
    if not isinstance(text, str):
        text = json.dumps(text)
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


# ─────────────────────────────────────────────────────────── tool handlers
def _tool_check_path(root, args):
    path = args.get("path", "")
    bundle = resolve.effective_bundle(root)
    rules = (((bundle.get("sdlc") or {}).get("sensitivity") or {}).get("rules")) or []
    for rule in rules:
        for pat in ((rule.get("match") or {}).get("paths") or []):
            if util.glob_match(pat, path):
                return {
                    "sensitive": True,
                    "level": rule.get("level"),
                    "require": rule.get("require") or [],
                }
    return {"sensitive": False, "level": None, "require": []}


def _tool_get_standards(root, args):
    bundle = resolve.effective_bundle(root)
    return (bundle.get("sdlc") or {}).get("standards") or []


def _tool_record(root, args):
    entry = {"event": args.get("event"), "ts": ledger.now()}
    for key in ("subject", "decision", "reason"):
        if args.get(key) is not None:
            entry[key] = args[key]
    appended = ledger.append(root, entry)
    return {"hash": appended["hash"], "seq": appended["seq"]}


def _tool_open_relay(root, args):
    run_id = args.get("run_id") or ledger.run_id_for_session(root, None)
    item = ledger.open_relay(root, run_id, args.get("reason", ""), {})
    return {"relay_id": item["relay_id"], "run_id": item["run_id"]}


def _tool_run_status(root, args):
    from . import run  # lazy: run.py is written in parallel

    run_id = args.get("run_id")
    if run_id:
        return run.load(root, run_id)
    return run.list_runs(root)


def _tool_submit_artifact(root, args):
    from . import run

    return run.submit_artifact(root, args["run_id"], args["name"], args.get("ref"))


def _tool_advance_run(root, args):
    from . import run

    return run.advance(root, args["run_id"])


_HANDLERS = {
    "check_path": _tool_check_path,
    "get_standards": _tool_get_standards,
    "record": _tool_record,
    "open_relay": _tool_open_relay,
    "run_status": _tool_run_status,
    "submit_artifact": _tool_submit_artifact,
    "advance_run": _tool_advance_run,
}

# Tools that depend on the (parallel) run module and may not be importable yet.
_RUN_TOOLS = {"run_status", "submit_artifact", "advance_run"}


def _call_tool(root, name, arguments):
    handler = _HANDLERS.get(name)
    if handler is None:
        return _content(f"unknown tool: {name}", is_error=True)
    arguments = arguments or {}
    try:
        return _content(handler(root, arguments), is_error=False)
    except ImportError:
        if name in _RUN_TOOLS:
            return _content(
                f"tool '{name}' unavailable: the 'run' module is not installed yet",
                is_error=True,
            )
        raise
    except Exception as exc:  # surface tool failures as isError, not transport errors
        return _content(f"{type(exc).__name__}: {exc}", is_error=True)


# ─────────────────────────────────────────────────────────── dispatch (core)
def dispatch(root, method, params, msg_id):
    """Turn a decoded JSON-RPC request into a response dict.

    Returns ``None`` for notifications (messages with no ``id``), which the
    caller must not reply to.
    """
    params = params or {}

    if method == "initialize":
        return _result(
            msg_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "agentic", "version": __version__},
            },
        )

    if method == "notifications/initialized":
        return None  # a notification: do not respond

    if method == "tools/list":
        return _result(msg_id, {"tools": TOOLS})

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not name:
            return _error(msg_id, _INVALID_PARAMS, "tools/call requires a 'name'")
        return _result(msg_id, _call_tool(root, name, arguments))

    # Unknown notification (has no id): stay silent.
    if msg_id is None:
        return None
    return _error(msg_id, _METHOD_NOT_FOUND, f"method not found: {method}")


# ─────────────────────────────────────────────────────────── stdio loop
def serve(root=None):
    """Read newline-delimited JSON-RPC from stdin, dispatch, write to stdout."""
    if root is None:
        root = util.find_project_root() or "."

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            resp = _error(None, -32700, "parse error")
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
            continue

        resp = dispatch(root, msg.get("method"), msg.get("params"), msg.get("id"))
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":  # pragma: no cover
    serve()
