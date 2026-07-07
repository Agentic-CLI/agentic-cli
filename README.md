# Agentic CLI — Proof of Concept

> A **supervisory framework** for agentic development. Not a place your agents run *inside* — a layer that **describes and supervises** the agents already running in Claude Code / Cursor, and records what they did as portable provenance.
>
> **Define** (one bundle) → **Compile** (project into any harness) → **Supervise** (gate at the harness's own hooks) → **Record** (append-only trust ledger).

This is a runnable POC for the direction in [`../PRD-PROVENANCE.md`](../PRD-PROVENANCE.md). **Zero dependencies** — runs on stock Python 3.9+ (uses PyYAML if present, otherwise a built-in YAML fallback).

## Why non-invasive

- **One directory added:** `.agentic/` (bundle + ledger). Everything else is *generated* and marked.
- **Observe before enforce:** provenance is reconstructed from what already exists (git, and later PRs/CI/session logs).
- **Out of the hot path:** control happens at Claude Code's official **hook** boundary, never by wrapping the agent. Remove Agentic and the generated `.claude/` still works.
- **Enforce only at declared gates:** paths the bundle marks *sensitive* block and open a human relay; everything else is recorded and proceeds.

## Quick start

```bash
alias agentic=/Users/yannick/Desktop/MSAI/agentic-cli/agentic

cd examples/todo-app
agentic init --name todo-app       # 1. Define: scaffold .agentic/bundle.yaml
agentic project                    # 2. Compile: generate .claude/ + AGENTS.md + hooks

# 3. Supervise (this is what Claude Code sends to the hook on every edit):
echo '{"session_id":"s1","cwd":"'$PWD'","tool_name":"Edit","tool_input":{"file_path":"src/todo/api.py"}}' | agentic gate          # exit 0  → allowed
echo '{"session_id":"s1","cwd":"'$PWD'","tool_name":"Write","tool_input":{"file_path":"src/todo/models/todo.py"}}' | agentic gate # exit 2 → BLOCKED, relay opened

# 4. Record / audit:
agentic ledger                     # the provenance trail (hash-chained)
agentic relay list                 # human-in-the-loop queue
agentic relay resolve <id> --approve --approver you@co
agentic observe --since "1 year ago"   # ingest git history, non-invasively
agentic doctor                     # bundle valid? config drift? ledger intact?
```

## Commands

| Command | Step | What it does |
|---|---|---|
| `agentic init` | Define | Scaffold `.agentic/bundle.yaml` (roles, lifecycle, gates, sensitivity) |
| `agentic project` | Compile | Generate `.claude/agents`, `.claude/skills`, `.claude/settings.json` (hooks), `AGENTS.md` |
| `agentic gate` | Supervise | PreToolUse hook handler: records to ledger; blocks sensitive paths + opens relay |
| `agentic ledger` / `trace <run_id>` | Record | Read the append-only, hash-chained provenance ledger |
| `agentic relay list` / `resolve` | Govern | Human-in-the-loop queue for blocked sensitive changes |
| `agentic observe` | Observe | Reconstruct provenance from git history (day-1, zero behavior change) |
| `agentic doctor` | — | Validate bundle, detect config drift, verify ledger integrity |

## Layout

```
agentic-cli/
├── agentic                 # zero-install launcher
├── pyproject.toml          # console entry point (agentic = agentic.cli:main)
├── src/agentic/
│   ├── bundle.py           # load / validate / scaffold the one source of truth
│   ├── projector.py        # Compile: bundle -> harness-native config
│   ├── gate.py             # Supervise: Claude Code hook handler
│   ├── ledger.py           # Record: append-only hash-chained ledger + relay
│   ├── observe.py          # Observe: reconstruct provenance from git
│   ├── _yaml.py            # PyYAML or built-in fallback (zero deps)
│   ├── util.py             # ULID, hash chain, glob, project-root discovery
│   └── cli.py              # command surface
└── examples/todo-app/      # dogfood target
```

## POC limitations (honest)

- Hash-chain integrity is a stand-in for **ed25519 signing** (production plan).
- One harness projector (Claude Code) + `AGENTS.md`; Cursor/others are next.
- `observe` ingests git only; PR/CI/session-log adapters are stubs for now.
- No cloud control plane, no `linked_runtime_runs` join yet (see PRD §10).
