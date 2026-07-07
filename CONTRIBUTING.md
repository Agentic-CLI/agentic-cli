# Contributing to Agentic CLI

Thanks for your interest! Agentic CLI is a **zero-dependency** Python project — that constraint is deliberate (it's part of "non-invasive"), so please keep runtime dependencies at zero. PyYAML is used *if present* but must never be required.

## Development setup

```bash
git clone https://github.com/Agentic-CLI/agentic-cli.git
cd agentic-cli
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
```

Or run the tool without installing anything, via the launcher:

```bash
./agentic --help
```

## Project layout

```
src/agentic/
├── cli.py          # command surface (argparse dispatch)
├── bundle.py       # load / validate / scaffold the bundle (source of truth)
├── projector.py    # Compile: render() → harness config (Claude Code, Cursor, AGENTS.md)
├── gate.py         # Supervise: Claude Code PreToolUse hook handler
├── ledger.py       # Record: append-only, hash-chained ledger + relay items
├── observe.py      # Observe: reconstruct provenance from git
├── _yaml.py        # PyYAML or built-in fallback (zero deps)
└── util.py         # ULID, hash chain, glob, project-root discovery
tests/              # pytest, standard-library only
examples/todo-app/  # dogfood target
```

## Guidelines

- **Zero runtime deps.** Standard library only. Tests may use `pytest`.
- **`projector.render()` is the single source of truth** for generated output — both `project` (write) and `doctor` (drift check) go through it. Don't duplicate rendering logic.
- **Type hints** on public functions; `from __future__ import annotations` at the top of modules.
- **Tests for behavior**, not implementation. The hash-chain tamper detection and YAML round-trip are load-bearing — keep them green.
- Lint with [ruff](https://docs.astral.sh/ruff/) (`ruff check .`) before opening a PR.
- Keep changes small and reversible; every PR should pass `pytest` and the CI smoke checks.

## Pull requests

1. Fork and branch (`feat/…`, `fix/…`).
2. Add or update tests.
3. Ensure `pytest` and `ruff check .` pass.
4. Open a PR describing the change and its motivation.

By contributing you agree your contributions are licensed under the project's [Apache-2.0](LICENSE) license.
