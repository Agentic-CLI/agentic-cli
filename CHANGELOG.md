# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `agentic init` — scaffold `.agentic/bundle.yaml` (roles, lifecycle, gates, sensitivity).
- `agentic project` — compile the bundle into `.claude/` (agents, skills, hooks), `.cursor/rules/`, and `AGENTS.md`.
- `agentic gate` — Claude Code `PreToolUse` hook handler: records to the ledger, blocks sensitive paths, opens a relay.
- `agentic ledger` / `trace` — append-only, hash-chained provenance ledger.
- `agentic relay list` / `resolve` — human-in-the-loop approval queue.
- `agentic observe` — reconstruct provenance from git history.
- `agentic doctor` — validate the bundle, detect config drift, verify ledger integrity.
- Reusable **packs** — `agentic add` / `agentic lock` resolve personas from any git repo (`extends: git::<repo>//<path>@<ref>`) with sha-pinned, reproducible resolution and per-repo `use:` / `overrides` merge. See [docs/PACKS.md](docs/PACKS.md).
- `-V` / `--version` flag and `install.sh` one-line installer (auto-detects uv → pipx → venv).
- Built-in zero-dependency YAML fallback (uses PyYAML when available).

[Unreleased]: https://github.com/Agentic-CLI/agentic-cli/commits/main
