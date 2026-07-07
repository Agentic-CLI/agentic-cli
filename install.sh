#!/usr/bin/env bash
#
# Agentic CLI installer.
#
#   curl -fsSL https://raw.githubusercontent.com/Agentic-CLI/agentic-cli/main/install.sh | bash
#
# Picks the best available method automatically:
#   uv  →  pipx  →  isolated venv (~/.local/share/agentic-cli)
# Zero runtime dependencies; needs uv, pipx, or Python 3.9+.
#
set -euo pipefail

REPO_SPEC="${AGENTIC_INSTALL_SPEC:-git+https://github.com/Agentic-CLI/agentic-cli.git}"
APP="agentic-cli"
BIN="agentic"

c_blue=$'\033[34m'; c_green=$'\033[32m'; c_red=$'\033[31m'; c_dim=$'\033[2m'; c_off=$'\033[0m'
info() { printf '%s::%s %s\n' "$c_blue" "$c_off" "$*"; }
ok()   { printf '%s✓%s %s\n'  "$c_green" "$c_off" "$*"; }
err()  { printf '%s✗%s %s\n'  "$c_red" "$c_off" "$*" >&2; }

info "Installing Agentic CLI…"

if command -v uv >/dev/null 2>&1; then
  info "Using ${c_dim}uv${c_off}"
  uv tool install --force "$REPO_SPEC"
elif command -v pipx >/dev/null 2>&1; then
  info "Using ${c_dim}pipx${c_off}"
  pipx install --force "$REPO_SPEC"
elif command -v python3 >/dev/null 2>&1; then
  info "uv/pipx not found — installing into an isolated venv at ${c_dim}~/.local/share/$APP${c_off}"
  VENV="$HOME/.local/share/$APP"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet "$REPO_SPEC"
  mkdir -p "$HOME/.local/bin"
  ln -sf "$VENV/bin/$BIN" "$HOME/.local/bin/$BIN"
  ok "Linked $HOME/.local/bin/$BIN"
  case ":$PATH:" in
    *":$HOME/.local/bin:"*) : ;;
    *) info "Add this to your shell profile:  ${c_dim}export PATH=\"\$HOME/.local/bin:\$PATH\"${c_off}" ;;
  esac
else
  err "Need uv, pipx, or Python 3.9+. Install Python from https://www.python.org/downloads/ and re-run."
  exit 1
fi

if command -v "$BIN" >/dev/null 2>&1; then
  ok "Installed $("$BIN" --version 2>/dev/null || echo "$BIN")"
  printf '\n%sGet started%s\n  %s init      %s# scaffold .agentic/bundle.yaml\n  %s project   %s# compile into .claude/, .cursor/, AGENTS.md\n' \
    "$c_green" "$c_off" "$BIN" "$c_dim$c_off" "$BIN" "$c_dim$c_off"
else
  ok "Installed. Restart your shell (or fix PATH), then run: $BIN --help"
fi
