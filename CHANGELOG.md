# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-07-07

Alpha. Parallel delivery, live observability, and lifecycle packs.

### Added
- **`agentic deliver`** — drive an epic (many work-items) through the lifecycle in isolated **git worktrees**, with collision-aware scheduling (disjoint items parallel, path-colliding items serialized) and a conflict-aware, sequential **merge queue** (`deliver start/schedule/status/merge`).
- **Live observability** — `agentic ledger --follow` (live tail) and a human-readable `.agentic/ledger/gate.log` written for every gate decision (allow and block).
- **Lifecycle packs** (`kind: lifecycle`) — reusable phase + gate + loop templates resolved via `extends` (local lifecycle wins; last pack wins). Completes the pack trio: persona / standard / lifecycle.

## [0.1.0] - 2026-07-07

First feature release: the local trust loop plus a governed workflow runner and an MCP surface for agents.

### Added
- **Workflow runner** — `agentic run start/advance/status/list/artifact` drives a unit of work through the lifecycle; advancing is **blocked until the phase's gate artifacts exist** (Definition-of-Ready / Definition-of-Done enforcement), and every transition is recorded in the ledger.
- **`agentic plan`** — scaffold and record the plan note (satisfies Definition of Ready).
- **Loop policy** — `sdlc.loops.<phase>: {until, max_attempts, on_exhausted}`; an exhausted loop escalates to a human relay.
- **`agentic mcp`** — MCP (stdio) server so agents can call agentic: `check_path`, `get_standards`, `run_status`, `submit_artifact`, `advance_run`, `record`, `open_relay`. Auto-registered via generated `.mcp.json` and `.cursor/mcp.json`.
- **`agentic status`** — overview of bundle, runs, pending relays, and ledger integrity.
- `agentic init` — scaffold `.agentic/bundle.yaml` (roles, lifecycle, gates, sensitivity).
- `agentic project` — compile the bundle into `.claude/` (agents, skills, hooks), `.cursor/rules/`, and `AGENTS.md`.
- `agentic gate` — Claude Code `PreToolUse` hook handler: records to the ledger, blocks sensitive paths, opens a relay.
- `agentic ledger` / `trace` — append-only, hash-chained provenance ledger.
- `agentic relay list` / `resolve` — human-in-the-loop approval queue.
- `agentic observe` — reconstruct provenance from git history.
- `agentic doctor` — validate the bundle, detect config drift, verify ledger integrity.
- Reusable **packs** — `agentic add` / `agentic lock` resolve **personas** (`kind: persona`, via `use:` + `overrides`) and **standards** (`kind: standard`, applied globally) from any git repo (`extends: git::<repo>//<path>@<ref>`), with sha-pinned reproducible resolution. Standards render into `AGENTS.md` and `.cursor/rules/standards.mdc`. See [docs/PACKS.md](docs/PACKS.md).
- `-V` / `--version` flag and `install.sh` one-line installer (auto-detects uv → pipx → venv).
- Built-in zero-dependency YAML fallback (uses PyYAML when available).

[Unreleased]: https://github.com/Agentic-CLI/agentic-cli/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Agentic-CLI/agentic-cli/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Agentic-CLI/agentic-cli/releases/tag/v0.1.0
