# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for security reports. Email
**security@agentic-cli.com** with details and reproduction steps. We aim to
acknowledge within 3 business days and will coordinate a fix and disclosure
timeline with you.

## Security posture of the tool itself

Agentic CLI is designed to be safe to run inside any repository:

- **No runtime dependencies.** Nothing is pulled from the network at runtime; the
  supply-chain surface is the standard library plus (optionally) PyYAML.
- **Local-first.** The trust ledger and relay items are plain files under
  `.agentic/`. Nothing leaves your machine unless you explicitly wire a cloud sync.
- **No secrets handled or stored.** The tool records *provenance metadata*
  (paths, decisions, run IDs) — not file contents, prompts, or credentials.
- **Tamper-evident ledger.** Entries are chained with SHA-256 so that editing or
  removing any past entry is detectable (`agentic doctor` verifies the chain).
  > Note: the hash chain is integrity-evident, not a cryptographic signature. Signed
  > provenance (ed25519) is on the roadmap; until then, treat the ledger as
  > tamper-*evident*, not tamper-*proof*.
- **Runs at the harness's own hook boundary** — it does not execute or modify agent
  code, and blocking a tool call fails safe (the action simply does not proceed).

## Supported versions

This project is pre-1.0 (alpha). Security fixes are applied to `main`.
