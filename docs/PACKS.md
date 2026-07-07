# Packs — reusable personas, standards & lifecycles

Author your personas, standards, lifecycles, and policies **once** in a git repo,
then reuse them across every project — pinned by version, merged with per-repo
overrides, and recorded in a sha-locked file so resolution is reproducible.

There is no hosted registry to depend on: **git is the registry.** A client keeps
a dedicated repo (e.g. `github.com/acme/agentic`); projects reference it.

## The three layers

```
Public packs  ──▶  Client repo (github.com/acme/agentic)  ──▶  Each project
(starter lib,       curated personas + standards,               .agentic/bundle.yaml
 community)         reused across all their repos               pins versions + overrides
```

The **client repo** is the middle layer — where an org's opinion lives, governed
by PRs + CODEOWNERS + CI in one place, private if they want (nothing leaves their
GitHub).

## Client-repo layout (convention)

```
acme/agentic/
├── personas/          # one file per persona
│   ├── security-reviewer.yaml
│   └── principal-architect.yaml
├── packs/             # standards / policy bundles (future)
├── lifecycles/        # phase + gate templates (future)
└── README.md
```

A **persona** file:

```yaml
kind: persona
id: security-reviewer
version: "0.1.0"
role: "Adversarial application-security reviewer. Never edits code."
capabilities: [read, grep, bash]
pairs_with: [feature-engineer]
refuses:
  - "secrets or credentials in code or logs"
  - "auth bypass / IDOR"
```

A **standard** pack (applies globally as context — no `use:` needed; renders into `AGENTS.md` and `.cursor/rules/standards.mdc`):

```yaml
kind: standard
id: payments-invariants
version: "0.1.0"
title: "Payment platform invariants"
rules:
  - "No floats for money — integer minor units only"
  - "Fail closed on compliance checks"
```

## Source syntax

Terraform-style, in a project's `.agentic/bundle.yaml`:

```
git::<repo-url>//<subpath>[@<ref>]
```

- `<repo-url>` — https, ssh, `file://`, or a local path
- `<subpath>` — path to the file inside the repo (after `//`)
- `<ref>` — commit, tag, or branch (resolved to a commit sha in the lockfile)

## Using a pack in a project

```yaml
# .agentic/bundle.yaml
schema_version: "1"
name: my-app
extends:
  - git::https://github.com/acme/agentic//personas/security-reviewer.yaml@v0.1.0
sdlc:
  roles:
    - use: security-reviewer          # inherit the canonical persona…
      owns: ["src/payment/**"]        # …with THIS repo's paths (local)
      overrides:
        refuses: ["floats for money"] # …and repo-specific additions (merged)
```

Or add it from the CLI:

```bash
agentic add git::https://github.com/acme/agentic//personas/security-reviewer.yaml@v0.1.0
agentic project        # compiles the persona into .claude/, .cursor/, AGENTS.md
```

### Merge semantics (`use` + `overrides`)

1. Start from the extended persona definition (`role`, `capabilities`, `refuses`, …).
2. Overlay this repo's local fields (`owns`, `pairs_with`, …).
3. Apply `overrides`: **lists are appended** (deduped); scalars are replaced.

Result: reuse the canonical persona, diverge explicitly per codebase — divergence
is a reviewable diff, not silent copy-paste drift.

## The lockfile (`.agentic/agentic.lock`)

Every resolved source is pinned to an exact commit + content hash:

```json
{
  "lock_version": "1",
  "sources": {
    "git::…/security-reviewer.yaml@v0.1.0": {
      "resolved_commit": "56f69fef902fb8405a382ebec76725369c88de92",
      "ref": "v0.1.0",
      "content_sha256": "d85c92e5…"
    }
  }
}
```

- **Commit it.** It makes resolution reproducible (tags move; shas don't).
- Resolution reuses the pinned commit until you run `agentic lock --update`.
- Because the exact version is known, the **trust ledger can record which pack
  version governed each decision** — governance whose *rules* are themselves
  provenance.

## Versioning convention (semver for prose)

- **major** — changes what gets gated/blocked (behavioral)
- **minor** — additive guidance
- **patch** — wording

Upgrades are deliberate (`agentic lock --update`) and reviewable — never silent.

## Commands

| Command | Does |
|---|---|
| `agentic add <git::source>` | Append an `extends` source, wire a `use:` role, write the lock |
| `agentic lock [--update]` | Resolve all sources and pin (or refresh) their shas |
| `agentic project` / `doctor` | Operate on the **effective** bundle (extends resolved + merged) |

## Security notes

- Private repos resolve via your existing git credentials — pack source never leaves your control.
- Always trust the **lockfile's sha**, not a floating tag, for reproducibility.
- Fetched packs are cached under `~/.agentic/cache` (override with `AGENTIC_CACHE`).

## Roadmap

- `lifecycles/` (phase+gate templates) via the same resolver, and standards → auto-generated gates
- ed25519-signed pack provenance
- a hosted registry (discovery, marketplace, private packs) — value **on top of** git, never required
